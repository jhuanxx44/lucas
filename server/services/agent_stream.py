"""新聊天链路：AgentRunner（harness single 模式）→ SSE 桥。

替代旧 stream.py（agents.Manager 链路，已删除）。事件协议与前端
web/src/hooks/useChat.ts 严格对齐：

  dispatch {researchers, mode}    run 开始（先于 researcher_start；
                                  useChat.ts 据此触发 onResearchTarget wiki 联动）
  researcher_start {id, name}     run 开始（固定 id="single"）
  tool_step {step, tool, args,    每个工具 step 完成，包含面板展示所需的
             ok, output, message} 结构化输入输出
  synthesis_chunk {text}          最终答案（逐 token 增量推送，前端增量拼接）
  researcher_done {id}            答案推送完成后
  done {total_tokens}             正常结束（AgentResult.usage 累计）
  error {message}                 异常 / 解析失败 / budget_exceeded / max_steps / timeout

actions 不再发送（前端缺省行为正常）。
"""
import asyncio
import json
import logging
from pathlib import Path
from typing import AsyncGenerator

from harness.config import build_single_system_prompt, load_agent_config
from harness.model_adapter import LLMClientAdapter
from harness.models import AgentResult, RunLimits
from harness.runner import AgentRunner, load_prompt_template
from harness.tools.business.stock import STOCK_KLINE_SPEC, STOCK_QUOTE_SPEC
from harness.tools.business.wiki import WIKI_RECALL_SPEC
from harness.tools.generic.web_search import WEB_SEARCH_SPEC
from harness.tools.registry import ToolRuntime
from utils.llm_client import create_client

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_PROMPT_PATH = _PROJECT_ROOT / "prompts" / "harness" / "agent-loop.md"

_HISTORY_TURNS = 10  # 注入 instruction 的最近对话轮数
_TIMEOUT_SECONDS = 120.0
_CHAT_TOOL_SPECS = [
    WEB_SEARCH_SPEC,
    STOCK_QUOTE_SPEC,
    STOCK_KLINE_SPEC,
    WIKI_RECALL_SPEC,
]
_CHAT_TOOL_NAMES = [spec.name for spec in _CHAT_TOOL_SPECS]


def _resolve_chat_tool_names(configured: list[str]) -> list[str]:
    """配置白名单与产品已注册工具取交集，保持配置顺序。"""
    return [name for name in configured if name in _CHAT_TOOL_NAMES]


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
    return f"Lucas 调用 {evt.get('tool')}: {hint}{suffix}"


def _error_message(result: AgentResult) -> str:
    """finish_reason → 中文友好文案（内部英文错误不外抛）"""
    if result.finish_reason == "budget_exceeded":
        return "本次分析超出成本预算，已中止。请缩小问题范围后重试。"
    if result.finish_reason == "max_steps":
        return "分析步骤达到上限仍未能得出结论。请把问题拆小后重试。"
    if result.finish_reason == "timeout":
        return "分析超时，已中止。请缩小问题范围后重试。"
    logger.warning("agent run 内部中断: finish_reason=%s error=%s",
                   result.finish_reason, result.error)
    return "分析过程中断，请稍后重试。"


async def chat_event_stream(
    question: str,
    history: list[dict] | None = None,
    user_id: str = "default",
    workspace: Path | None = None,
    model_adapter=None,
) -> AsyncGenerator[str, None]:
    run_task: asyncio.Task | None = None
    try:
        config = load_agent_config()
        # 产品聊天显式装配四个只读研究工具；wiki 根 = 工作区/wiki。
        tools = ToolRuntime(workspace or _PROJECT_ROOT, _CHAT_TOOL_SPECS)
        allowed_tools = _resolve_chat_tool_names(config.allowed_tools)
        if model_adapter is None:
            # 工具说明渲染进 system prompt（稳定指令层），user prompt 只留每轮变化内容。
            system_prompt = build_single_system_prompt(tools.describe(allowed_tools))
            client = create_client(provider=config.provider, model=config.model,
                                   system_prompt=system_prompt)
            model_adapter = LLMClientAdapter(client, temperature=config.temperature)
        runner = AgentRunner(model_adapter, tools, load_prompt_template(_PROMPT_PATH))
        instruction = _render_history(history) + f"用户问题：{question}"
        limits = RunLimits(max_steps=config.max_steps, timeout_seconds=_TIMEOUT_SECONDS)

        queue: asyncio.Queue = asyncio.Queue()
        run_task = asyncio.create_task(
            runner.run(instruction, allowed_tools, limits,
                       on_event=queue.put_nowait, stream_answer=True)
        )

        # answer_chunk 已推送的字符数；run 结束时若少于最终答案长度则补尾防缺字
        streamed_chars = 0

        def _forward(evt: dict) -> str | None:
            nonlocal streamed_chars
            kind = evt.get("kind")
            if kind == "tool_step":
                return _sse("tool_step", {
                    "step": evt.get("step"),
                    "tool": evt.get("tool"),
                    "args": evt.get("args") or {},
                    "ok": bool(evt.get("ok")),
                    "output": evt.get("observation", ""),
                    "message": _status_message(evt),
                })
            if kind == "answer_chunk":
                text = evt.get("text", "")
                streamed_chars += len(text)
                return _sse("synthesis_chunk", {"text": text})
            if kind == "answer":
                # Runner 权威计数（含流式回退前的部分推送）
                streamed_chars = evt.get("streamed_chars", streamed_chars)
            return None

        yield _sse("dispatch", {
            "researchers": [{"id": "single", "name": config.name}],
            "mode": "single",
        })
        yield _sse("researcher_start", {"id": "single", "name": config.name})
        # 运行期间增量排出工具 step / answer_chunk 事件；
        # answer 事件以最终 AgentResult 为准，不重复推送
        while not run_task.done():
            try:
                evt = await asyncio.wait_for(queue.get(), timeout=0.05)
            except asyncio.TimeoutError:
                continue
            out = _forward(evt)
            if out is not None:
                yield out
        result = run_task.result()
        while not queue.empty():
            out = _forward(queue.get_nowait())
            if out is not None:
                yield out

        if result.finish_reason == "completed" and result.answer is not None:
            text = result.answer if isinstance(result.answer, str) else json.dumps(
                result.answer, ensure_ascii=False)
            if streamed_chars < len(text):
                # 解析器保守缓冲（工具步/结构化 answer/回退）时整段或补尾推送
                yield _sse("synthesis_chunk", {"text": text[streamed_chars:]})
            yield _sse("researcher_done", {"id": "single"})
            total_tokens = result.usage.total_tokens if result.usage else 0
            yield _sse("done", {"total_tokens": total_tokens})
        else:
            yield _sse("error", {"message": _error_message(result)})
    except Exception:
        logger.exception("agent stream error for question: %s", question[:80])
        # 内部异常（含 provider 英文报错、掩码 key 等）不外抛，统一中文兜底
        yield _sse("error", {"message": "分析过程出错，请稍后重试。"})
    finally:
        # 客户端断开（GeneratorExit）或异常退出时取消 run，不再继续烧 token
        if run_task is not None and not run_task.done():
            run_task.cancel()
