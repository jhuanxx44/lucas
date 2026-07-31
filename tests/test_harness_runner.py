import asyncio
import json
from pathlib import Path

import pytest

from harness.models import FunctionCall, ModelRequest, ModelTurn, RunLimits
from harness.runner import AgentRunner
from harness.tools.base import ToolResult, ToolSpec
from harness.tools.generic.filesystem import READ_FILE_SPEC
from harness.tools.registry import ToolRuntime
from harness.trace import TraceRecorder
from utils.token_tracker import TokenUsage


PROMPT = "规则：使用原生工具；完成后直接回答。\n任务：{instruction}"


def _answer(text="done", *, usage=None, response_id="resp_answer"):
    return ModelTurn(
        output_text=text,
        usage=usage,
        response_id=response_id,
        response_items=[{"type": "message", "id": response_id, "content": text}],
    )


def _tool(name, args, *, call_id="call_1", summary="先执行这一步", usage=None):
    raw = json.dumps({**args, "summary": summary}, ensure_ascii=False)
    return ModelTurn(
        function_calls=[FunctionCall(call_id, name, args, summary, raw)],
        usage=usage,
        response_id=f"resp_{call_id}",
        response_items=[{
            "type": "function_call",
            "call_id": call_id,
            "name": name,
            "arguments": raw,
        }],
    )


class FakeModel:
    def __init__(self, turns):
        self.turns = list(turns)
        self.requests: list[ModelRequest] = []

    async def complete(self, request: ModelRequest):
        self.requests.append(request)
        value = self.turns.pop(0)
        if isinstance(value, Exception):
            raise value
        if callable(value):
            value = value(request)
        return value


def _runner(tmp_path: Path, model, specs=None, **kwargs):
    tools = ToolRuntime(tmp_path, specs or [READ_FILE_SPEC])
    return AgentRunner(model, tools, PROMPT, instructions="system", **kwargs)


def _limits(max_steps=10, timeout=0, cost=0):
    return RunLimits(max_steps=max_steps, timeout_seconds=timeout, max_cost_usd=cost)


def _events(trace):
    return [json.loads(line) for line in trace.path.read_text().splitlines()]


@pytest.mark.asyncio
async def test_native_tool_call_round_trip_uses_provider_call_id(tmp_path):
    (tmp_path / "config.yaml").write_text("model: deepseek\n", encoding="utf-8")
    model = FakeModel([
        _tool("read_file", {"path": "config.yaml"}, call_id="provider-call-7"),
        _answer("finished"),
    ])

    result = await _runner(tmp_path, model).run(
        "read config", ["read_file"], _limits()
    )

    assert result.answer == "finished"
    assert len(model.requests) == 2
    second_items = model.requests[1].input_items
    assert second_items[-2]["type"] == "function_call"
    assert second_items[-1]["type"] == "function_call_output"
    assert second_items[-1]["call_id"] == "provider-call-7"
    assert "model: deepseek" in second_items[-1]["output"]


@pytest.mark.asyncio
async def test_summary_is_emitted_before_tool_step_and_not_forwarded_to_handler(tmp_path):
    seen_args = []

    def handler(workspace, args):
        seen_args.append(args)
        return ToolResult(status="ok", observation="ok")

    spec = ToolSpec(
        name="echo",
        description="echo",
        parameters={
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
            "additionalProperties": False,
        },
        handler=handler,
    )
    model = FakeModel([_tool("echo", {"value": "x"}, summary="我先确认一下"), _answer()])
    events = []

    await _runner(tmp_path, model, [spec]).run(
        "echo", ["echo"], _limits(), on_event=events.append
    )

    assert seen_args == [{"value": "x"}]
    assert [event["kind"] for event in events[:2]] == ["summary", "tool_step"]
    assert events[0]["text"] == "我先确认一下"


@pytest.mark.asyncio
async def test_commentary_with_one_tool_call_is_not_treated_as_final_answer(tmp_path):
    turn = _tool("read_file", {"path": "config.yaml"}, summary="读取现有配置")
    turn.commentary = "我先看一下现有配置。"
    (tmp_path / "config.yaml").write_text("model: deepseek\n", encoding="utf-8")
    model = FakeModel([turn, _answer("完成")])
    trace = TraceRecorder(tmp_path / "trace.jsonl", "commentary-run")

    result = await _runner(tmp_path, model).run(
        "读取配置", ["read_file"], _limits(), trace=trace
    )

    assert result.answer == "完成"
    assert len(model.requests) == 2
    assert any(event["event"] == "model_commentary" for event in _events(trace))


@pytest.mark.asyncio
async def test_direct_output_text_finishes_without_tool(tmp_path):
    model = FakeModel([_answer("plain answer")])

    result = await _runner(tmp_path, model).run("answer", [], _limits())

    assert result.finish_reason == "completed"
    assert result.answer == "plain answer"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid",
    [
        ModelTurn(protocol_error="bad arguments"),
        ModelTurn(output_text="text", function_calls=[
            FunctionCall("c1", "read_file", {"path": "x"}, "summary")
        ]),
        ModelTurn(function_calls=[
            FunctionCall("c1", "read_file", {"path": "x"}, "one"),
            FunctionCall("c2", "read_file", {"path": "y"}, "two"),
        ]),
        ModelTurn(),
    ],
)
async def test_invalid_native_decision_is_corrected_without_executing_tool(tmp_path, invalid):
    model = FakeModel([invalid, _answer("recovered")])

    result = await _runner(tmp_path, model).run("task", ["read_file"], _limits())

    assert result.answer == "recovered"
    assert model.requests[1].input_items[-1]["role"] == "user"
    assert "不符合工具协议" in model.requests[1].input_items[-1]["content"]


@pytest.mark.asyncio
async def test_protocol_correction_has_independent_bound(tmp_path):
    model = FakeModel([ModelTurn()] * 4)

    result = await _runner(tmp_path, model).run("task", [], _limits(max_steps=10))

    assert result.finish_reason == "protocol_error"
    assert len(model.requests) == 4


@pytest.mark.asyncio
async def test_repeated_failed_call_is_not_executed_twice(tmp_path):
    call = _tool("read_file", {"path": "../escape"})
    model = FakeModel([call, call, _answer("fallback")])
    events = []

    result = await _runner(tmp_path, model).run(
        "read", ["read_file"], _limits(), on_event=events.append
    )

    assert result.answer == "fallback"
    second_output = model.requests[2].input_items[-1]
    assert second_output["type"] == "function_call_output"
    assert "连续两次" in second_output["output"]
    tool_steps = [event for event in events if event["kind"] == "tool_step"]
    assert len(tool_steps) == 2
    assert tool_steps[-1]["ok"] is False


@pytest.mark.asyncio
async def test_repeated_success_observation_injects_stall_note(tmp_path):
    spec = ToolSpec(
        name="same",
        description="same",
        parameters={"type": "object", "properties": {}, "required": [], "additionalProperties": False},
        handler=lambda workspace, args: ToolResult(status="ok", observation="same output"),
    )
    model = FakeModel([
        _tool("same", {}, call_id="c1"),
        _tool("same", {}, call_id="c2"),
        _answer(),
    ])

    await _runner(tmp_path, model, [spec]).run("same", ["same"], _limits())

    assert "停滞" in model.requests[2].input_items[-1]["output"]


@pytest.mark.asyncio
async def test_trace_preserves_native_response_and_tool_events(tmp_path):
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
    trace = TraceRecorder(tmp_path / "trace.jsonl", "run-1")
    model = FakeModel([_tool("read_file", {"path": "a.txt"}), _answer("done")])

    await _runner(tmp_path, model).run(
        "read", ["read_file"], _limits(), trace=trace
    )

    names = [event["event"] for event in _events(trace)]
    assert "model_input_prepared" in names
    assert "response_started" in names
    assert "function_call_received" in names
    assert "tool_call_started" in names
    assert "tool_call_finished" in names
    assert "function_call_output" in names
    assert "assistant_answer" in names
    assert (tmp_path / "artifacts" / "input-step-1.json").is_file()
    assert (tmp_path / "artifacts" / "output-step-1.json").is_file()


@pytest.mark.asyncio
async def test_trace_records_provider_retries_separately_from_model_corrections(tmp_path):
    turn = _answer("done")
    turn.provider_retries = [{
        "retry_count": 1,
        "next_attempt": 2,
        "delay_seconds": 3,
        "error_type": "RuntimeError",
        "status_code": 503,
    }]
    trace = TraceRecorder(tmp_path / "trace.jsonl", "retry-run")

    await _runner(tmp_path, FakeModel([turn])).run(
        "answer", [], _limits(), trace=trace
    )

    events = _events(trace)
    retry_events = [event for event in events if event["event"] == "provider_retry"]
    assert [event["data"]["retry_count"] for event in retry_events] == [1]
    assert not any(event["event"] == "model_correction" for event in events)


@pytest.mark.asyncio
async def test_usage_is_accumulated_across_responses(tmp_path):
    first = TokenUsage(prompt_tokens=10, completion_tokens=2, thinking_tokens=3,
                       total_tokens=15, model="m")
    second = TokenUsage(prompt_tokens=20, completion_tokens=4, thinking_tokens=5,
                        total_tokens=29, model="m")
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    model = FakeModel([
        _tool("read_file", {"path": "a.txt"}, usage=first),
        _answer("done", usage=second),
    ])

    result = await _runner(tmp_path, model).run("read", ["read_file"], _limits())

    assert result.usage.prompt_tokens == 30
    assert result.usage.completion_tokens == 6
    assert result.usage.thinking_tokens == 8
    assert result.usage.total_tokens == 44


@pytest.mark.asyncio
async def test_cost_budget_is_checked_before_tool_execution(tmp_path):
    calls = []
    spec = ToolSpec(
        name="touch",
        description="touch",
        parameters={"type": "object", "properties": {}, "required": [], "additionalProperties": False},
        handler=lambda workspace, args: calls.append(args) or ToolResult(status="ok"),
    )
    costly = TokenUsage(completion_tokens=1_000_000, total_tokens=1_000_000, model="m")
    model = FakeModel([_tool("touch", {}, usage=costly)])

    result = await _runner(tmp_path, model, [spec]).run(
        "touch", ["touch"], _limits(cost=0.01)
    )

    assert result.finish_reason == "budget_exceeded"
    assert calls == []


@pytest.mark.asyncio
async def test_cost_budget_is_checked_before_accepting_final_answer(tmp_path):
    costly = TokenUsage(completion_tokens=1_000_000, total_tokens=1_000_000, model="m")
    model = FakeModel([_answer("over budget", usage=costly)])
    events = []

    result = await _runner(tmp_path, model).run(
        "answer", [], _limits(cost=0.01), on_event=events.append
    )

    assert result.finish_reason == "budget_exceeded"
    assert result.answer is None
    assert not any(event["kind"] == "answer" for event in events)


@pytest.mark.asyncio
async def test_max_steps_terminates_native_loop(tmp_path):
    model = FakeModel([_tool("read_file", {"path": "missing"})])

    result = await _runner(tmp_path, model).run(
        "read", ["read_file"], _limits(max_steps=1)
    )

    assert result.finish_reason == "max_steps"


@pytest.mark.asyncio
async def test_run_deadline_covers_model_call(tmp_path):
    class SlowModel:
        async def complete(self, request):
            await asyncio.sleep(0.05)
            return _answer()

    result = await _runner(tmp_path, SlowModel()).run(
        "slow", [], _limits(timeout=0.01)
    )

    assert result.finish_reason == "timeout"
    assert "exceeded timeout" in result.error


@pytest.mark.asyncio
async def test_provider_timeout_before_deadline_is_not_misclassified(tmp_path):
    model = FakeModel([TimeoutError("provider request timed out")])

    with pytest.raises(TimeoutError, match="provider request timed out"):
        await _runner(tmp_path, model).run("task", [], _limits(timeout=10))


@pytest.mark.asyncio
async def test_run_deadline_covers_async_tool(tmp_path):
    async def handler(workspace, args):
        await asyncio.sleep(0.05)
        return ToolResult(status="ok")

    spec = ToolSpec(
        name="slow",
        description="slow",
        parameters={"type": "object", "properties": {}, "required": [], "additionalProperties": False},
        handler=handler,
    )
    model = FakeModel([_tool("slow", {})])

    result = await _runner(tmp_path, model, [spec]).run(
        "slow", ["slow"], _limits(timeout=0.01)
    )

    assert result.finish_reason == "timeout"


@pytest.mark.asyncio
async def test_unknown_tool_is_returned_as_native_function_output(tmp_path):
    model = FakeModel([_tool("missing", {}), _answer("handled")])

    result = await _runner(tmp_path, model).run("task", [], _limits())

    assert result.answer == "handled"
    assert "unknown tool" in model.requests[1].input_items[-1]["output"]
