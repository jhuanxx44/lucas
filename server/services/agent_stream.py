"""新聊天链路：AgentRunner（harness single 模式）→ SSE 桥。

替代旧 stream.py（agents.Manager 链路，已删除）。事件协议与前端
web/src/hooks/useChat.ts 严格对齐：

  dispatch {researchers, mode}    run 开始（先于 researcher_start；
                                  useChat.ts 据此触发 onResearchTarget wiki 联动）
  researcher_start {id, name}     run 开始（固定 id="single"）
  summary {step, text}            模型原生 function call 的 summary 参数，
                                  展示为过程摘要；不传给业务工具。
                                  模型原生 reasoning 草稿仅记入 trace，不再推送前端
  tool_start {step, tool, args,   工具开始执行，前端立即展示运行中状态
              message}
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
from dataclasses import replace
from datetime import date, datetime
import time
from pathlib import Path
from typing import AsyncGenerator

from harness.config import build_single_system_prompt, load_agent_config
from harness.model_adapter import ResponsesModelAdapter, responses_tools
from harness.models import AgentResult, RunLimits
from harness.runner import AgentRunner, load_prompt_template
from harness.tools.base import ToolResult
from harness.tools.business.stock import STOCK_KLINE_SPEC, STOCK_QUOTE_SPEC
from harness.tools.business.wiki import WIKI_RECALL_SPEC
from harness.tools.generic.filesystem import (
    APPLY_PATCH_SPEC,
    LIST_FILES_SPEC,
    READ_FILE_SPEC,
    SEARCH_SPEC,
    WRITE_FILE_SPEC,
)
from harness.tools.generic.web_search import WEB_SEARCH_SPEC
from harness.tools.generic.planning import UPDATE_PLAN_SPEC
from harness.tools.registry import ToolRuntime
from utils.llm_client import create_client
from utils.path_safety import resolve_within

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_PROMPT_PATH = _PROJECT_ROOT / "prompts" / "harness" / "agent-loop.md"


def _guard_wiki_write(handler):
    """聊天链路的写入策略：只允许改动 wiki/ 知识库。

    聊天工作区根 = 项目根，未加限制的写工具会碰到 raw/（不可变原始输入）、
    .git、harness 代码等。写操作统一收窄到 wiki/ 目录内。读操作不受限。
    """
    def guarded(workspace: Path, args: dict) -> ToolResult:
        rel = args.get("path")
        if not isinstance(rel, str) or not rel or Path(rel).is_absolute():
            return ToolResult(status="denied", error_code="write_scope",
                              observation="写入被拒绝：只能修改 wiki/ 知识库下的文件")
        ws_root = workspace.resolve()
        wiki_root = ws_root / "wiki"
        target = resolve_within(ws_root, ws_root / rel, strict=False)
        if target is None or (target != wiki_root and wiki_root not in target.parents):
            return ToolResult(status="denied", error_code="write_scope",
                              observation="写入被拒绝：只能修改 wiki/ 知识库下的文件")
        return handler(workspace, args)
    return guarded


# 写工具限定 wiki/；读工具（read_file/list_files/search）跨工作区只读，无需 guard。
_WIKI_WRITE_FILE_SPEC = replace(
    WRITE_FILE_SPEC,
    description="在 wiki/ 知识库内新建或整体写入文件（仅限 wiki/ 目录）；"
                "文件已存在时默认拒绝，需 overwrite: true 才覆盖",
    handler=_guard_wiki_write(WRITE_FILE_SPEC.handler),
)
_WIKI_APPLY_PATCH_SPEC = replace(
    APPLY_PATCH_SPEC,
    description="对 wiki/ 知识库内文件做精确字符串替换（仅限 wiki/ 目录；old 必须唯一出现）",
    handler=_guard_wiki_write(APPLY_PATCH_SPEC.handler),
)

_HISTORY_TURNS = 10  # 注入 instruction 的最近对话轮数
_TIMEOUT_SECONDS = 0.0  # 0 = 不限时
_CHAT_TOOL_SPECS = [
    UPDATE_PLAN_SPEC,
    WEB_SEARCH_SPEC,
    STOCK_QUOTE_SPEC,
    STOCK_KLINE_SPEC,
    WIKI_RECALL_SPEC,
    READ_FILE_SPEC,
    LIST_FILES_SPEC,
    SEARCH_SPEC,
    _WIKI_WRITE_FILE_SPEC,
    _WIKI_APPLY_PATCH_SPEC,
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


_WEEKDAYS = "一二三四五六日"


def _render_date_header() -> str:
    """注入当前日期——模型训练截止会误以为现在是过去，日期必须由代码保证"""
    now = datetime.now()
    return (
        f"当前日期：{now:%Y-%m-%d}（星期{_WEEKDAYS[now.weekday()]}）。"
        "涉及「最新」「近期」「最近」等时间表述时以此为准，搜索查询和财务数据解读都要考虑该日期。\n\n"
    )


def _status_message(evt: dict) -> str:
    """工具 step → status 文案，如「调用 web_search: 贵州茅台 年报」"""
    args = evt.get("args") or {}
    tool = evt.get("tool", "?")
    hint = ""
    if tool == "update_plan":
        steps = args.get("steps", args.get("plan", []))
        if isinstance(steps, str):
            steps = [{"step": steps}]
        if isinstance(steps, list) and steps:
            hint = "、".join(s.get("step", "") for s in steps[:3] if isinstance(s, dict))
            if len(steps) > 3:
                hint += f" 等{len(steps)}步"
            hint = f"计划: {hint}"
        else:
            hint = "（空计划）"
    else:
        for key in ("query", "code", "path"):
            if isinstance(args.get(key), str):
                hint = args[key]
                break
        if not hint:
            hint = json.dumps(args, ensure_ascii=False)
    if len(hint) > 60:
        hint = hint[:60] + "…"
    suffix = "（失败）" if "ok" in evt and not evt.get("ok") else ""
    return f"Lucas 调用 {tool}: {hint}{suffix}"


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
    model_override: str | None = None,
) -> AsyncGenerator[str, None]:
    run_task: asyncio.Task | None = None
    try:
        config = load_agent_config()
        # 产品聊天显式装配四个只读研究工具；wiki 根 = 工作区/wiki。
        tools = ToolRuntime(workspace or _PROJECT_ROOT, _CHAT_TOOL_SPECS)
        allowed_tools = _resolve_chat_tool_names(config.allowed_tools)
        model = model_override or config.model
        system_prompt = build_single_system_prompt(current_date=date.today().isoformat())
        if model_adapter is None:
            logger.info("━━ 收到问题 | model=%s | %s", model, question[:100])
            client = create_client(model=model)
            model_adapter = ResponsesModelAdapter(client)
        prompt_template = load_prompt_template(_PROMPT_PATH)
        runner = AgentRunner(
            model_adapter,
            tools,
            prompt_template,
            instructions=system_prompt,
            temperature=config.temperature,
        )
        # 非寒暄问题强制标注：提醒模型必须使用工具查证
        chitchat_patterns = ('hi', 'hello', '你好', '谢谢', '你是谁', '你是什么', '你叫什么')
        is_chitchat = question.strip().lower().startswith(chitchat_patterns) and len(question) < 15
        tool_tag = "" if is_chitchat else "⚠️ 本条问题需要查证外部事实，禁止凭记忆直接回答。先调用 wiki_recall 或 web_search。\n\n"


        instruction = _render_date_header() + _render_history(history) + tool_tag + f"用户问题：{question}"
        limits = RunLimits(max_steps=0, timeout_seconds=_TIMEOUT_SECONDS)  # 0 = 不限步数

        queue: asyncio.Queue = asyncio.Queue()
        run_task = asyncio.create_task(
            runner.run(instruction, allowed_tools, limits,
                       on_event=queue.put_nowait,
                       on_trace_event=queue.put_nowait,
                       stream_answer=True)
        )

        t0 = time.monotonic()
        # answer_chunk 已推送的字符数；run 结束时若少于最终答案长度则补尾防缺字
        streamed_chars = 0
        step_count = 0

        _pending_reasoning: dict[int, str] = {}

        def _flush_reasoning(step: int) -> str | None:
            text = _pending_reasoning.pop(step, None)
            if text:
                return _sse("trace_event", {
                    "event": "model_reasoning",
                    "step": step,
                    "data": {"text": text},
                })
            return None

        def _forward(evt: dict):
            nonlocal streamed_chars, step_count
            kind = evt.get("kind")
            if kind == "model_input":
                yield _sse("trace_event", {
                    "event": "model_input",
                    "step": evt.get("step"),
                    "data": {"input": evt.get("input", [])},
                })
            if kind == "model_output":
                yield _sse("trace_event", {
                    "event": "model_output",
                    "step": evt.get("step"),
                    "data": {
                        "response_id": evt.get("response_id", ""),
                        "output_text": evt.get("output_text", ""),
                        "items": evt.get("items", []),
                    },
                })
            if kind == "thought":
                step = evt.get("step", 0)
                _pending_reasoning[step] = _pending_reasoning.get(step, "") + evt.get("text", "")
                return
            if kind == "tool_start":
                yield _sse("tool_start", {
                    "step": evt.get("step"),
                    "tool": evt.get("tool", "?"),
                    "args": evt.get("args") or {},
                    "message": _status_message(evt),
                })
            if kind == "tool_step":
                tool_name = evt.get("tool", "?")
                ok = bool(evt.get("ok"))
                obs = evt.get("observation", "")
                step_count = evt.get("step", 0)
                logger.info("  📎 step %s | %s %s → %s (%d chars)",
                            step_count,
                            "✅" if ok else "❌",
                            tool_name,
                            "ok" if ok else "fail",
                            len(obs))
                yield _sse("tool_step", {
                    "step": evt.get("step"),
                    "tool": tool_name,
                    "args": evt.get("args") or {},
                    "ok": ok,
                    "output": obs,
                    "message": _status_message(evt),
                })
                if tool_name == "update_plan" and ok:
                    plan_data = evt.get("args", {})
                    plan_steps = plan_data.get("steps", plan_data.get("plan", []))
                    if isinstance(plan_steps, str):
                        plan_steps = [{"step": plan_steps, "status": "in_progress"}]
                    yield _sse("plan_update", {
                        "plan": plan_steps,
                    })
            if kind == "summary":
                text = evt.get("text", "")
                if text:
                    logger.info("  💬 step %s summary: %s", evt.get("step"), text[:120])
                yield _sse("summary", {
                    "step": evt.get("step"),
                    "text": text,
                })
            if kind == "answer_chunk":
                text = evt.get("text", "")
                streamed_chars += len(text)
                yield _sse("synthesis_chunk", {"text": text})
            if kind == "answer":
                # Runner 权威计数（含流式回退前的部分推送）
                streamed_chars = evt.get("streamed_chars", streamed_chars)
                step_count = evt.get("step", step_count)
            return

        yield _sse("dispatch", {
            "researchers": [{"id": "single", "name": config.name}],
            "mode": "single",
        })
        yield _sse("researcher_start", {"id": "single", "name": config.name})
        yield _sse("trace_event", {
            "event": "run_started",
            "data": {"question": question},
        })
        yield _sse("trace_event", {
            "event": "run_config",
            "data": {
                "agent": config.name,
                "protocol": "openai_responses",
                "model": model,
                "temperature": config.temperature,
                "allowed_tools": allowed_tools,
                "max_steps": limits.max_steps,
                "timeout_seconds": limits.timeout_seconds,
                "system_prompt": system_prompt,
                "tools": responses_tools(tools.available(allowed_tools)),
                "prompt_template": prompt_template,
            },
        })
        # 运行期间增量排出工具 step / answer_chunk 事件；
        # answer 事件以最终 AgentResult 为准，不重复推送
        while not run_task.done():
            try:
                evt = await asyncio.wait_for(queue.get(), timeout=0.05)
            except asyncio.TimeoutError:
                continue
            for out in _forward(evt):
                if out is not None:
                    yield out
        # 排空当前 step 的累积 reasoning
        cur_step = max(_pending_reasoning.keys()) if _pending_reasoning else 0
        flush = _flush_reasoning(cur_step)
        if flush:
            yield flush
        result = run_task.result()
        while not queue.empty():
            for out in _forward(queue.get_nowait()):
                if out is not None:
                    yield out
        # 排空所有剩余累积 reasoning
        for step in sorted(_pending_reasoning.keys()):
            flush = _flush_reasoning(step)
            if flush:
                yield flush

        if result.finish_reason == "completed" and result.answer is not None:
            text = result.answer if isinstance(result.answer, str) else json.dumps(
                result.answer, ensure_ascii=False)
            answer_len = len(text)
            if streamed_chars < answer_len:
                yield _sse("synthesis_chunk", {"text": text[streamed_chars:]})
            yield _sse("trace_event", {
                "event": "assistant_answer",
                "step": step_count,
                "data": {"answer": text},
            })
            yield _sse("trace_event", {
                "event": "run_finished",
                "data": {"finishReason": result.finish_reason},
            })
            yield _sse("researcher_done", {"id": "single"})
            total_tokens = result.usage.total_tokens if result.usage else 0
            elapsed = time.monotonic() - t0
            logger.info("  ✅ 回答完成 | %d 步, %d tokens, %d chars, %.1fs",
                        step_count, total_tokens, answer_len, elapsed)
            yield _sse("done", {"total_tokens": total_tokens})
        else:
            elapsed = time.monotonic() - t0
            logger.warning("  ⚠️ 非正常结束 | finish_reason=%s, %.1fs",
                           result.finish_reason, elapsed)
            yield _sse("trace_event", {
                "event": "run_finished",
                "data": {
                    "finishReason": result.finish_reason,
                    "error": result.error,
                },
            })
            yield _sse("error", {"message": _error_message(result)})
    except Exception:
        logger.exception("agent stream error for question: %s", question[:80])
        # 内部异常（含 provider 英文报错、掩码 key 等）不外抛，统一中文兜底
        yield _sse("error", {"message": "分析过程出错，请稍后重试。"})
    finally:
        # 客户端断开（GeneratorExit）或异常退出时取消 run，不再继续烧 token
        if run_task is not None and not run_task.done():
            run_task.cancel()
