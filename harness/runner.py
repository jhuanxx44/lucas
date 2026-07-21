import asyncio
import json
import time
from pathlib import Path
from typing import Callable

from harness.model_adapter import ModelAdapter
from harness.models import AgentResult, RunLimits, StepContext
from harness.streaming import AnswerStreamParser
from harness.tools.registry import ToolRuntime
from harness.trace import TraceRecorder
from utils.token_tracker import TokenUsage

MAX_OBSERVATION_CHARS = 16_000
MAX_TOTAL_OBSERVATION_CHARS = 48_000


class _RunDeadlineExceeded(Exception):
    pass


class _NullTrace:
    """trace 为空时的 no-op 替代，保持 Runner 主循环不做分支判断"""

    def record(self, event: str, data: dict | None = None) -> None:
        return None


def load_prompt_template(path: str | Path) -> str:
    """加载 prompt 模板并剥离 frontmatter（--- ... ---）"""
    text = Path(path).read_text(encoding="utf-8")
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[end + 4:].lstrip("\n")
    return text


class AgentRunner:
    """通用最小 Agent 循环：模型每轮返回一个 JSON（tool 或 answer）"""

    def __init__(self, model: ModelAdapter, tools: ToolRuntime, prompt_template: str):
        self.model = model
        self.tools = tools
        self.prompt_template = prompt_template

    async def run(
        self,
        instruction: str,
        allowed_tools: list[str],
        limits: RunLimits,
        trace: TraceRecorder | None = None,
        on_event: Callable[[dict], None] | None = None,
        stream_answer: bool = False,
    ) -> AgentResult:
        """on_event：可选的 step 事件钩子（同步回调，零开销缺省）。

        工具执行完成时回调 {"kind": "tool_step", "step", "tool", "args", "ok",
        "observation"}；
        answer 产出时回调 {"kind": "answer", "step", "answer"}。
        不改变任何终止语义，仅用于外部观察（如 SSE 桥）。

        stream_answer=True 且 adapter 实现 complete_stream 且传了 on_event 时，
        模型输出改走流式：AnswerStreamParser 确认是字符串 reply 后逐段回调
        {"kind": "answer_chunk", "step", "text"}；完整 raw 仍走与非流式
        一字不差的 _parse_action / trace / 全量回放逻辑，answer 事件额外带
        streamed_chars（已推送字符数，供下游补尾）。默认 False，evals 零变化。
        流式调用抛异常时记 trace 后回退 complete()，run 不中断。
        """
        context = StepContext(step_id="", instruction=instruction)
        last_failed_signature = None
        total_observation_chars = 0
        total_usage: TokenUsage | None = None
        cost_usd = 0.0
        run_started = time.monotonic()
        deadline = (
            run_started + limits.timeout_seconds
            if limits.timeout_seconds and limits.timeout_seconds > 0 else None
        )
        artifacts: Path | None = None
        if trace is not None:
            artifacts = trace.path.parent / "artifacts"
            artifacts.mkdir(exist_ok=True)
        else:
            trace = _NullTrace()

        async def await_before_deadline(awaitable):
            if deadline is None:
                return await awaitable
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                if hasattr(awaitable, "close"):
                    awaitable.close()
                raise _RunDeadlineExceeded
            try:
                return await asyncio.wait_for(awaitable, timeout=remaining)
            except TimeoutError as e:
                if time.monotonic() >= deadline:
                    raise _RunDeadlineExceeded from e
                raise

        def timeout_result(phase: str) -> AgentResult:
            elapsed = time.monotonic() - run_started
            trace.record("timeout", {
                "step_id": context.step_id,
                "phase": phase,
                "elapsed_seconds": round(elapsed, 3),
                "timeout_seconds": limits.timeout_seconds,
            })
            return AgentResult(
                finish_reason="timeout",
                error=f"elapsed {elapsed:.1f}s exceeded timeout {limits.timeout_seconds}s",
                usage=total_usage, cost_usd=cost_usd,
            )

        for step in range(1, limits.max_steps + 1):
            if deadline is not None and time.monotonic() >= deadline:
                return timeout_result("between_steps")
            context.step_id = f"step-{step}"
            trace.record("step_started", {"step_id": context.step_id})
            prompt = self._render(context, allowed_tools)
            # 大 payload 写 artifact，trace 只留引用；prompt 不含敏感信息（工作区隔离、env 已净化）
            prompt_ref = (
                _write_artifact(artifacts, f"prompt-{context.step_id}.txt", prompt)
                if artifacts is not None else None
            )
            trace.record("prompt_rendered", {
                "step_id": context.step_id,
                "prompt_chars": len(prompt),
                "artifact": prompt_ref,
            })
            trace.record("model_call_started", {
                "step_id": context.step_id, "model_call_id": f"model-{step}",
            })
            started = time.monotonic()
            # 流式路径需 on_event 承接 answer_chunk；evals 默认走非流式 complete()
            use_stream = (
                stream_answer
                and on_event is not None
                and hasattr(self.model, "complete_stream")
            )
            stream_state = {"streamed": 0}
            try:
                if use_stream:
                    try:
                        raw, usage = await await_before_deadline(
                            self._complete_streaming(prompt, step, on_event, stream_state))
                    except _RunDeadlineExceeded:
                        return timeout_result("model_call")
                    except Exception as e:
                        trace.record("answer_stream_fallback", {
                            "step_id": context.step_id, "error": str(e)[:200],
                        })
                        raw, usage = await await_before_deadline(
                            self.model.complete(prompt))
                else:
                    raw, usage = await await_before_deadline(
                        self.model.complete(prompt))
            except _RunDeadlineExceeded:
                return timeout_result("model_call")
            duration_ms = (time.monotonic() - started) * 1000
            if usage is not None:
                total_usage = usage if total_usage is None else total_usage.merge(usage)
            cost_usd = total_usage.total_cost if total_usage is not None else 0.0
            output_ref = (
                _write_artifact(artifacts, f"output-{context.step_id}.txt", raw)
                if artifacts is not None else None
            )
            trace.record("model_call_finished", {
                "step_id": context.step_id,
                "model_call_id": f"model-{step}",
                "duration_ms": round(duration_ms, 1),
                "output_chars": len(raw),
                "artifact": output_ref,
                **(_usage_trace_data(usage)),
            })
            # 全量回放：模型自己的原始输出（包括格式错误的）进入后续上下文
            context.history.append({"role": "assistant", "content": raw})
            action = _parse_action(raw)
            if action is None:
                trace.record("action_parsed", {
                    "step_id": context.step_id, "kind": "invalid",
                })
                context.history.append({"role": "tool", "content": (
                    "你的上一条回复格式不对。请返回且只返回一个 JSON 对象："
                    '调用工具用 {"action": "tool", "tool": "工具名", "args": {...}}；'
                    '最终作答用 {"action": "answer", "reply": "答案"}。'
                    "如果答案本身是 JSON，请把它作为 reply 的字符串值或直接用其内容作答。"
                )})
                trace.record("step_finished", {"step_id": context.step_id})
                continue

            # summary：面向用户的一句话旁白，解析后即刻发出（先于工具执行/答案返回）
            summary = action.get("summary")
            if summary and on_event is not None:
                on_event({"kind": "summary", "step": step, "text": summary})

            if action["kind"] == "answer":
                answer_text = action["answer"]
                trace.record("action_parsed", {
                    "step_id": context.step_id,
                    "kind": "answer",
                    "answer_preview": str(answer_text)[:500],
                })
                trace.record("step_finished", {"step_id": context.step_id})
                if on_event is not None:
                    event = {"kind": "answer", "step": step, "answer": answer_text}
                    if use_stream:
                        # 已推送字符数（含回退前部分推送），供下游补尾防缺字
                        event["streamed_chars"] = stream_state["streamed"]
                    on_event(event)
                return AgentResult(
                    answer=answer_text, finish_reason="completed",
                    usage=total_usage, cost_usd=cost_usd,
                )

            tool, args = action["tool"], action["args"]
            trace.record("action_parsed", {
                "step_id": context.step_id, "kind": "tool", "tool": tool, "args": args,
            })
            signature = (tool, json.dumps(args, sort_keys=True, ensure_ascii=False))
            if signature == last_failed_signature:
                trace.record("step_finished", {"step_id": context.step_id})
                return AgentResult(
                    finish_reason="error",
                    error=f"repeated failing tool call aborted: {tool}",
                    usage=total_usage, cost_usd=cost_usd,
                )
            # 预算在执行下一个工具前检查：已产出的最终答案不会被预算拦截丢弃
            if limits.max_cost_usd and cost_usd > limits.max_cost_usd:
                trace.record("budget_exceeded", {
                    "step_id": context.step_id,
                    "cost_usd": round(cost_usd, 6),
                    "max_cost_usd": limits.max_cost_usd,
                })
                trace.record("step_finished", {"step_id": context.step_id})
                return AgentResult(
                    finish_reason="budget_exceeded",
                    error=f"cost {cost_usd:.4f} USD exceeded budget {limits.max_cost_usd} USD",
                    usage=total_usage, cost_usd=cost_usd,
                )
            if total_observation_chars >= MAX_TOTAL_OBSERVATION_CHARS:
                trace.record("observation_budget_exceeded", {
                    "step_id": context.step_id,
                    "total_observation_chars": total_observation_chars,
                    "max_total_observation_chars": MAX_TOTAL_OBSERVATION_CHARS,
                })
                trace.record("step_finished", {"step_id": context.step_id})
                return AgentResult(
                    finish_reason="error",
                    error="tool observation budget exhausted",
                    usage=total_usage, cost_usd=cost_usd,
                )
            call_id = f"call-{step}"
            trace.record("tool_call_started", {
                "tool_call_id": call_id, "tool": tool, "args": args,
            })
            try:
                result = await await_before_deadline(
                    self.tools.execute(tool, args, allowed_tools))
            except _RunDeadlineExceeded:
                return timeout_result("tool_call")
            full_observation = _format_observation(tool, result)
            remaining_observation_chars = (
                MAX_TOTAL_OBSERVATION_CHARS - total_observation_chars
            )
            observation, was_truncated = _truncate_observation(
                full_observation,
                min(MAX_OBSERVATION_CHARS, remaining_observation_chars),
            )
            if was_truncated:
                result.truncated = True
            total_observation_chars += len(observation)
            if result.ok:
                trace.record("tool_call_finished", {
                    "tool_call_id": call_id,
                    "observation_chars": len(observation),
                    "total_observation_chars": total_observation_chars,
                    "observation": observation,
                    "truncated": result.truncated,
                })
                last_failed_signature = None
            else:
                trace.record("tool_call_error", {
                    "tool_call_id": call_id,
                    "status": result.status,
                    "error_code": result.error_code,
                })
                last_failed_signature = signature
            context.history.append({"role": "tool", "content": observation})
            trace.record("step_finished", {"step_id": context.step_id})
            if on_event is not None:
                on_event({
                    "kind": "tool_step",
                    "step": step,
                    "tool": tool,
                    "args": args,
                    "ok": result.ok,
                    "observation": observation,
                })
        return AgentResult(
            finish_reason="max_steps", error="max steps exhausted",
            usage=total_usage, cost_usd=cost_usd,
        )

    async def _complete_streaming(
        self,
        prompt: str,
        step: int,
        on_event: Callable[[dict], None],
        stream_state: dict,
    ) -> tuple[str, TokenUsage | None]:
        """流式调用模型：区分模型原生的思考通道与答案通道。

        - reasoning 段：逐段回调 {"kind":"thought"}，展示为过程思考；不进 raw。
        - content 段：累积为 raw（喂 _parse_action / 全量回放），并经
          AnswerStreamParser 提取字符串 reply 后回调 answer_chunk。
          工具调用/结构化 answer/非法输出不发 answer_chunk。
        流式无 usage，记 None。
        """
        parser = AnswerStreamParser()
        parts: list[str] = []
        async for kind, text in self.model.complete_stream(prompt):
            if kind == "reasoning":
                # 原生思考通道：逐段推送为过程 thought，不进 raw（不影响动作解析与回放）
                if text:
                    on_event({"kind": "thought", "step": step, "text": text})
                continue
            # content 段：累积为 raw（喂 _parse_action / 全量回放），并经 parser 提取 reply
            parts.append(text)
            for delta in parser.feed(text):
                stream_state["streamed"] += len(delta)
                on_event({"kind": "answer_chunk", "step": step, "text": delta})
        for delta in parser.finalize():
            stream_state["streamed"] += len(delta)
            on_event({"kind": "answer_chunk", "step": step, "text": delta})
        return "".join(parts), None

    def _render(self, context: StepContext, allowed_tools: list[str]) -> str:
        # 工具说明由调用方拼进 system prompt（稳定指令层），此处只渲染每轮变化的
        # 任务与历史观察。allowed_tools 仍传入以保持 run() 签名不变（execute 用）。
        labels = {"assistant": "【你】", "tool": "【工具】"}
        observations = "\n\n".join(
            f"{labels[m['role']]}{m['content']}" for m in context.history
        ) or "（暂无）"
        return self.prompt_template.format(
            instruction=context.instruction,
            observations=observations,
        )


def _write_artifact(artifacts: Path, name: str, content: str) -> str:
    path = artifacts / name
    path.write_text(content, encoding="utf-8")
    return f"artifacts/{name}"


def _usage_trace_data(usage: TokenUsage | None) -> dict:
    if usage is None:
        return {}
    return {
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
        "total_tokens": usage.total_tokens,
    }


def _parse_action(raw: str) -> dict | None:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]) if len(lines) >= 2 else text.strip("`")
    try:
        value = json.loads(text.strip())
    except json.JSONDecodeError:
        return None
    if not isinstance(value, dict):
        return None
    # summary：给用户看的一句话旁白（可选），不影响动作语义
    raw_summary = value.get("summary")
    summary = raw_summary.strip() if isinstance(raw_summary, str) and raw_summary.strip() else None
    if value.get("action") == "answer":
        answer = value.get("reply", value.get("answer"))
        if answer is None:
            return None
        return {"kind": "answer", "answer": answer, "summary": summary}
    if value.get("action") == "tool" and isinstance(value.get("tool"), str):
        args = value.get("args", {})
        if not isinstance(args, dict):
            return None
        return {"kind": "tool", "tool": value["tool"], "args": args, "summary": summary}
    if "action" not in value:
        # 宽容解析：模型直接输出答案 JSON（无 action 外壳）时按 answer 接受
        return {"kind": "answer", "answer": value, "summary": summary}
    return None


def _format_observation(tool: str, result) -> str:
    suffix = " [truncated]" if result.truncated else ""
    return f"[{tool}] status={result.status}{suffix}\n{result.observation}"


def _truncate_observation(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    marker = "\n…[tool observation truncated]"
    if limit <= 0:
        return "", True
    if limit <= len(marker):
        return marker[:limit], True
    return text[:limit - len(marker)] + marker, True
