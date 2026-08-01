import asyncio
import hashlib
import json
import time
from pathlib import Path
from typing import Callable

from harness.model_adapter import ModelAdapter
from harness.models import AgentResult, ModelRequest, ModelTurn, RunLimits, StepContext
from harness.tools.registry import ToolRuntime
from harness.trace import TraceRecorder
from utils.token_tracker import TokenUsage

MAX_OBSERVATION_CHARS = 10_000_000
MAX_MODEL_CORRECTIONS = 3


class _RunDeadlineExceeded(Exception):
    pass


class _NullTrace:
    def record(self, event: str, data: dict | None = None) -> None:
        return None


def load_prompt_template(path: str | Path) -> str:
    """Load a prompt template and strip its llm-weight frontmatter."""
    text = Path(path).read_text(encoding="utf-8")
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[end + 4:].lstrip("\n")
    return text


class AgentRunner:
    """Native Responses loop; Lucas owns execution and explicit context items."""

    def __init__(
        self,
        model: ModelAdapter,
        tools: ToolRuntime,
        prompt_template: str,
        instructions: str = "",
        temperature: float = 0.0,
    ):
        self.model = model
        self.tools = tools
        self.prompt_template = prompt_template
        self.instructions = instructions
        self.temperature = temperature

    async def run(
        self,
        instruction: str,
        allowed_tools: list[str],
        limits: RunLimits,
        trace: TraceRecorder | None = None,
        on_event: Callable[[dict], None] | None = None,
        stream_answer: bool = False,
        on_trace_event: Callable[[dict], None] | None = None,
    ) -> AgentResult:
        initial_input = self.prompt_template.format(instruction=instruction)
        context = StepContext(
            step_id="",
            instruction=instruction,
            input_items=[{"role": "user", "content": initial_input}],
        )
        last_failed_signature = None
        seen_result_steps: dict[str, int] = {}
        stall_count = 0
        correction_count = 0
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
            except TimeoutError as error:
                if time.monotonic() >= deadline:
                    raise _RunDeadlineExceeded from error
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
                usage=total_usage,
                cost_usd=cost_usd,
            )

        step = 0
        while limits.max_steps <= 0 or step < limits.max_steps:
            step += 1
            if deadline is not None and time.monotonic() >= deadline:
                return timeout_result("between_steps")
            context.step_id = f"step-{step}"
            trace.record("step_started", {"step_id": context.step_id})

            request = ModelRequest(
                instructions=self.instructions,
                input_items=list(context.input_items),
                tools=self.tools.available(allowed_tools),
                temperature=self.temperature,
            )
            serialized_input = json.dumps(request.input_items, ensure_ascii=False, indent=2)
            input_ref = (
                _write_artifact(artifacts, f"input-{context.step_id}.json", serialized_input)
                if artifacts is not None else None
            )
            trace.record("model_input_prepared", {
                "step_id": context.step_id,
                "input_items": len(request.input_items),
                "input_chars": len(serialized_input),
                "artifact": input_ref,
            })
            if on_trace_event is not None:
                on_trace_event({"kind": "model_input", "step": step, "input": request.input_items})
            trace.record("model_call_started", {
                "step_id": context.step_id,
                "model_call_id": f"model-{step}",
            })
            trace.record("response_started", {"step_id": context.step_id})

            use_stream = stream_answer and on_event is not None and hasattr(self.model, "complete_stream")
            # 已实时推送的 answer 字符数；流式中途失败回退 complete() 时仍保留，
            # 供下游按最终答案补尾防缺字。
            stream_state = {"streamed": 0}
            started = time.monotonic()
            try:
                if use_stream:
                    try:
                        turn = await await_before_deadline(
                            self._complete_streaming(request, step, on_event, stream_state)
                        )
                    except _RunDeadlineExceeded:
                        return timeout_result("model_call")
                    except Exception as error:
                        trace.record("answer_stream_fallback", {
                            "step_id": context.step_id,
                            "error": str(error)[:200],
                        })
                        turn = await await_before_deadline(self.model.complete(request))
                else:
                    turn = await await_before_deadline(self.model.complete(request))
            except _RunDeadlineExceeded:
                return timeout_result("model_call")

            if turn.function_calls and stream_state["streamed"] > 0 and on_event is not None:
                # 工具轮（含被拒绝的混合轮）流出的 output_text 只是中间叙述，
                # 不是最终答案，通知下游清掉已展示的临时文本
                on_event({"kind": "answer_discard"})

            duration_ms = (time.monotonic() - started) * 1000
            if turn.usage is not None:
                total_usage = turn.usage if total_usage is None else total_usage.merge(turn.usage)
            cost_usd = total_usage.total_cost if total_usage is not None else 0.0
            output_json = json.dumps(turn.response_items, ensure_ascii=False, indent=2)
            output_ref = (
                _write_artifact(artifacts, f"output-{context.step_id}.json", output_json)
                if artifacts is not None else None
            )
            trace.record("model_call_finished", {
                "step_id": context.step_id,
                "model_call_id": f"model-{step}",
                "duration_ms": round(duration_ms, 1),
                "output_chars": len(turn.output_text),
                "output_items": len(turn.response_items),
                "response_id": turn.response_id,
                "artifact": output_ref,
                **_usage_trace_data(turn.usage),
            })
            trace.record("response_completed", {
                "step_id": context.step_id,
                "response_id": turn.response_id,
                "output_items": len(turn.response_items),
            })
            for retry in turn.provider_retries:
                trace.record("provider_retry", {
                    "step_id": context.step_id,
                    **retry,
                })
            if turn.reasoning:
                trace.record("model_reasoning", {
                    "step_id": context.step_id,
                    "text": turn.reasoning,
                })
            if turn.commentary:
                trace.record("model_commentary", {
                    "step_id": context.step_id,
                    "text": turn.commentary,
                })
            if on_trace_event is not None:
                on_trace_event({
                    "kind": "model_output",
                    "step": step,
                    "response_id": turn.response_id,
                    "output_text": turn.output_text,
                    "items": turn.response_items,
                })

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
                    usage=total_usage,
                    cost_usd=cost_usd,
                )

            decision_error = _decision_error(turn)
            if decision_error:
                correction_count += 1
                trace.record("model_correction", {
                    "step_id": context.step_id,
                    "reason": decision_error,
                    "correction_count": correction_count,
                })
                trace.record("step_finished", {"step_id": context.step_id})
                if correction_count > MAX_MODEL_CORRECTIONS:
                    return AgentResult(
                        finish_reason="protocol_error",
                        error=f"model protocol correction exhausted: {decision_error}",
                        usage=total_usage,
                        cost_usd=cost_usd,
                    )
                context.input_items.append({
                    "role": "user",
                    "content": (
                        f"上一响应不符合工具协议：{decision_error}。"
                        "请重新作出一次决策：需要工具时只返回一个 function_call item；"
                        "任务完成时只返回最终答案。"
                    ),
                })
                continue

            correction_count = 0
            if not turn.function_calls:
                answer_text = turn.output_text
                trace.record("assistant_answer", {
                    "step_id": context.step_id,
                    "answer_preview": answer_text[:500],
                })
                trace.record("step_finished", {"step_id": context.step_id})
                if on_event is not None:
                    on_event({
                        "kind": "answer",
                        "step": step,
                        "answer": answer_text,
                        "streamed_chars": stream_state["streamed"],
                    })
                return AgentResult(
                    answer=answer_text,
                    finish_reason="completed",
                    usage=total_usage,
                    cost_usd=cost_usd,
                )

            call = turn.function_calls[0]
            tool, args = call.name, call.arguments
            trace.record("function_call_received", {
                "step_id": context.step_id,
                "tool_call_id": call.call_id,
                "tool": tool,
                "args": args,
                "summary": call.summary,
            })
            if on_event is not None:
                on_event({"kind": "summary", "step": step, "text": call.summary})

            signature = (tool, json.dumps(args, sort_keys=True, ensure_ascii=False))
            if signature == last_failed_signature:
                observation = (
                    f"警告：{tool} 连续两次以相同参数调用失败。"
                    "请换用其他工具、换一组参数，或基于已有信息作答。"
                )
                trace.record("tool_call_repeated_failure", {
                    "step_id": context.step_id,
                    "tool": tool,
                    "args": args,
                })
                _append_function_output(context, turn, call.call_id, observation)
                trace.record("function_call_output", {
                    "tool_call_id": call.call_id,
                    "observation": observation,
                })
                trace.record("step_finished", {"step_id": context.step_id})
                if on_event is not None:
                    on_event({
                        "kind": "tool_step",
                        "step": step,
                        "tool": tool,
                        "args": args,
                        "ok": False,
                        "observation": observation,
                    })
                continue

            trace.record("tool_call_started", {
                "tool_call_id": call.call_id,
                "tool": tool,
                "args": args,
            })
            if on_event is not None:
                on_event({
                    "kind": "tool_start",
                    "step": step,
                    "tool": tool,
                    "args": args,
                })
            try:
                result = await await_before_deadline(self.tools.execute(tool, args, allowed_tools))
            except _RunDeadlineExceeded:
                return timeout_result("tool_call")
            full_observation = _format_observation(tool, result)
            remaining_observation_chars = max(0, MAX_OBSERVATION_CHARS - total_observation_chars)
            observation, was_truncated = _truncate_observation(
                full_observation,
                min(MAX_OBSERVATION_CHARS, remaining_observation_chars),
            )
            if was_truncated:
                result.truncated = True
            total_observation_chars += len(observation)

            if result.ok:
                trace.record("tool_call_finished", {
                    "tool_call_id": call.call_id,
                    "observation_chars": len(observation),
                    "total_observation_chars": total_observation_chars,
                    "observation": observation,
                    "truncated": result.truncated,
                })
                last_failed_signature = None
                result_hash = hashlib.sha256(observation.encode("utf-8")).hexdigest()
                first_step = seen_result_steps.get(result_hash)
                if first_step is not None:
                    stall_count += 1
                    function_output = _stall_note(tool, first_step)
                    trace.record("no_progress_detected", {
                        "step_id": context.step_id,
                        "tool": tool,
                        "repeated_from_step": first_step,
                        "stall_count": stall_count,
                    })
                else:
                    seen_result_steps[result_hash] = step
                    function_output = observation
            else:
                trace.record("tool_call_error", {
                    "tool_call_id": call.call_id,
                    "status": result.status,
                    "error_code": result.error_code,
                })
                last_failed_signature = signature
                function_output = observation

            _append_function_output(context, turn, call.call_id, function_output)
            trace.record("function_call_output", {
                "tool_call_id": call.call_id,
                "observation": function_output,
            })
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
            finish_reason="max_steps",
            error="max steps exhausted",
            usage=total_usage,
            cost_usd=cost_usd,
        )

    async def _complete_streaming(
        self,
        request: ModelRequest,
        step: int,
        on_event: Callable[[dict], None],
        stream_state: dict,
    ) -> ModelTurn:
        """实时转发答案 delta；completed turn 提供最终答案与 usage。

        DeepSeek 工具轮也可能产出 output_text.delta（中间叙述，item 顺序
        不可靠），因此文本一律实时转发，由本 runner 在 turn 完成且确认
        是工具轮后发出 answer_discard 丢弃。
        """
        completed_turn: ModelTurn | None = None
        async for event in self.model.complete_stream(request):
            if event.kind == "reasoning_delta":
                if event.text:
                    on_event({"kind": "thought", "step": step, "text": event.text})
            elif event.kind == "output_text_delta":
                stream_state["streamed"] += len(event.text)
                on_event({"kind": "answer_chunk", "step": step, "text": event.text})
            elif event.kind == "completed":
                completed_turn = event.turn
        if completed_turn is None:
            raise RuntimeError("model stream did not produce a completed turn")
        return completed_turn


def _decision_error(turn: ModelTurn) -> str:
    if turn.protocol_error:
        return turn.protocol_error
    if len(turn.function_calls) > 1:
        return "response returned more than one function call"
    if turn.function_calls and turn.output_text.strip():
        return "response mixed a function call with final output text"
    if not turn.function_calls and not turn.output_text.strip():
        return "response contained neither a function call nor final output text"
    return ""


def _append_function_output(
    context: StepContext,
    turn: ModelTurn,
    call_id: str,
    output: str,
) -> None:
    context.input_items.extend(turn.response_items)
    context.input_items.append({
        "type": "function_call_output",
        "call_id": call_id,
        "output": output,
    })


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
        "thinking_tokens": usage.thinking_tokens,
        "total_tokens": usage.total_tokens,
    }


def _format_observation(tool: str, result) -> str:
    suffix = " [truncated]" if result.truncated else ""
    return f"[{tool}] status={result.status}{suffix}\n{result.observation}"


def _stall_note(tool: str, first_step: int) -> str:
    return (
        f"⚠️ 停滞：{tool} 返回结果与第 {first_step} 步完全相同，"
        "继续当前方式不会获得新信息。\n"
        "先盘点已经掌握的内容，想想还缺什么——然后换个思路再试。"
    )


def _truncate_observation(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    marker = "\n…[tool observation truncated]"
    if limit <= 0:
        return "", True
    if limit <= len(marker):
        return marker[:limit], True
    return text[:limit - len(marker)] + marker, True
