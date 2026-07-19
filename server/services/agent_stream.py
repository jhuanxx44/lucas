"""新聊天链路：AgentRunner（harness single 模式）→ SSE 桥。

替代旧 stream.py（agents.Manager 链路，M6 删除）。事件协议与前端
web/src/hooks/useChat.ts 严格对齐：

  researcher_start {id, name}     run 开始（固定 id="single"）
  status {message}                每个工具 step 完成
  synthesis_chunk {text}          最终答案（事件级流式，整段一次推送）
  researcher_done {id}            答案推送完成后
  done {total_tokens}             正常结束（AgentResult.usage 累计）
  error {message}                 异常 / 解析失败 / budget_exceeded / max_steps

dispatch / actions 不再发送（前端缺省行为正常）。
"""
import asyncio
import json
import logging
from pathlib import Path
from typing import AsyncGenerator

from harness.config import load_agent_config
from harness.model_adapter import LLMClientAdapter
from harness.models import AgentResult, RunLimits
from harness.runner import AgentRunner, load_prompt_template
from harness.tools.business import BUSINESS_TOOL_SPECS
from harness.tools.registry import ToolRuntime
from utils.llm_client import create_client

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_PROMPT_PATH = _PROJECT_ROOT / "prompts" / "harness" / "tool-loop.md"

_HISTORY_TURNS = 10  # 注入 instruction 的最近对话轮数
_TIMEOUT_SECONDS = 120.0


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _render_history(history: list[dict] | None) -> str:
    """把会话历史渲染进 instruction 文本（Runner 无消息结构）"""
    if not history:
        return ""
    lines = []
    for turn in history[-_HISTORY_TURNS:]:
        content = (turn.get("content") or "").strip()
        if not content:
            continue
        label = "用户" if turn.get("role") == "user" else "助手"
        lines.append(f"{label}: {content}")
    if not lines:
        return ""
    return "以下是本次对话的历史记录（仅用于理解上下文，不要复述）：\n" + "\n".join(lines) + "\n\n"


def _status_message(evt: dict) -> str:
    """工具 step → status 文案，如「调用 web_search: 贵州茅台 年报」"""
    args = evt.get("args") or {}
    hint = ""
    for key in ("query", "code", "path"):
        if isinstance(args.get(key), str):
            hint = args[key]
            break
    if not hint:
        hint = json.dumps(args, ensure_ascii=False)
    if len(hint) > 60:
        hint = hint[:60] + "…"
    suffix = "" if evt.get("ok") else "（失败）"
    return f"调用 {evt.get('tool')}: {hint}{suffix}"


def _error_message(result: AgentResult) -> str:
    """finish_reason → 中文友好文案"""
    if result.finish_reason == "budget_exceeded":
        return "本次分析超出成本预算，已中止。请缩小问题范围后重试。"
    if result.finish_reason == "max_steps":
        return "分析步骤达到上限仍未能得出结论。请把问题拆小后重试。"
    return f"分析过程中断：{result.error or '未知原因'}"


async def chat_event_stream(
    question: str,
    history: list[dict] | None = None,
    user_id: str = "default",
    workspace: Path | None = None,
    model_adapter=None,
) -> AsyncGenerator[str, None]:
    try:
        config = load_agent_config()
        if model_adapter is None:
            client = create_client(provider=config.provider, model=config.model)
            model_adapter = LLMClientAdapter(client, temperature=config.temperature)
        # 聊天链路只挂业务工具（只读取数）；wiki 根 = 工作区/wiki，由 server 侧装配传入
        tools = ToolRuntime(workspace or _PROJECT_ROOT, BUSINESS_TOOL_SPECS)
        runner = AgentRunner(model_adapter, tools, load_prompt_template(_PROMPT_PATH))
        instruction = _render_history(history) + f"用户问题：{question}"
        limits = RunLimits(max_steps=config.max_steps, timeout_seconds=_TIMEOUT_SECONDS)

        queue: asyncio.Queue = asyncio.Queue()
        run_task = asyncio.create_task(
            runner.run(instruction, config.allowed_tools, limits,
                       on_event=queue.put_nowait)
        )

        yield _sse("researcher_start", {"id": "single", "name": config.name})
        # 运行期间增量排出工具 step 事件；answer 事件以最终 AgentResult 为准，不重复推送
        while not run_task.done():
            try:
                evt = await asyncio.wait_for(queue.get(), timeout=0.05)
            except asyncio.TimeoutError:
                continue
            if evt.get("kind") == "tool_step":
                yield _sse("status", {"message": _status_message(evt)})
        result = run_task.result()
        while not queue.empty():
            evt = queue.get_nowait()
            if evt.get("kind") == "tool_step":
                yield _sse("status", {"message": _status_message(evt)})

        if result.finish_reason == "completed" and result.answer is not None:
            text = result.answer if isinstance(result.answer, str) else json.dumps(
                result.answer, ensure_ascii=False)
            yield _sse("synthesis_chunk", {"text": text})
            yield _sse("researcher_done", {"id": "single"})
            total_tokens = result.usage.total_tokens if result.usage else 0
            yield _sse("done", {"total_tokens": total_tokens})
        else:
            yield _sse("error", {"message": _error_message(result)})
    except Exception as e:
        logger.exception("agent stream error for question: %s", question[:80])
        yield _sse("error", {"message": f"分析过程出错：{e}"})
