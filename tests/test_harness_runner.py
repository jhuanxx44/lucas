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


def _parallel_tool_turn(calls):
    """构造一个含多个 function_call 的 ModelTurn（并行工具调用）。

    calls: [(call_id, name, args, summary), ...]
    """
    function_calls = []
    response_items = []
    for call_id, name, args, summary in calls:
        raw = json.dumps({**args, "summary": summary}, ensure_ascii=False)
        function_calls.append(FunctionCall(call_id, name, args, summary, raw))
        response_items.append({
            "type": "function_call",
            "call_id": call_id,
            "name": name,
            "arguments": raw,
        })
    return ModelTurn(
        function_calls=function_calls,
        response_id=f"resp_{function_calls[0].call_id}",
        response_items=response_items,
    )


class FakeModel:
    def __init__(self, turns, summary_text=None, summary_error=None):
        self.turns = list(turns)
        self.summary_text = summary_text
        self.summary_error = summary_error
        self.requests: list[ModelRequest] = []
        self.summary_requests: list[ModelRequest] = []

    async def complete(self, request: ModelRequest):
        self.requests.append(request)
        if not request.tools and request.instructions == "":
            # 链式压缩的 LLM 摘要调用：独立记录，不走主循环 turns
            self.summary_requests.append(request)
            if self.summary_error is not None:
                if isinstance(self.summary_error, Exception):
                    raise self.summary_error
                return _answer("")
            return _answer(self.summary_text or "已完成这些步骤的工具调用，关键事实已记录于本摘要。")
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
async def test_parallel_tool_calls_execute_all_and_append_all_outputs(tmp_path):
    (tmp_path / "a.txt").write_text("alpha", encoding="utf-8")
    (tmp_path / "b.txt").write_text("beta", encoding="utf-8")
    model = FakeModel([
        _parallel_tool_turn([
            ("c1", "read_file", {"path": "a.txt"}, "读 a"),
            ("c2", "read_file", {"path": "b.txt"}, "读 b"),
        ]),
        _answer("done"),
    ])

    result = await _runner(tmp_path, model).run("read", ["read_file"], _limits())

    assert result.answer == "done"
    assert len(model.requests) == 2
    items = model.requests[1].input_items
    # 模型 items 只追加一次；两个 output 都带各自 call_id 且顺序在 function_call 之后
    calls = [i for i in items if i.get("type") == "function_call"]
    outputs = [i for i in items if i.get("type") == "function_call_output"]
    assert len(calls) == 2
    assert len(outputs) == 2
    assert [i.get("call_id") for i in outputs] == ["c1", "c2"]
    assert "alpha" in outputs[0]["output"] and "beta" in outputs[1]["output"]
    assert items.index(calls[-1]) < items.index(outputs[0])


@pytest.mark.asyncio
async def test_parallel_tool_calls_partial_failure_returns_all_outputs(tmp_path):
    (tmp_path / "a.txt").write_text("alpha", encoding="utf-8")
    model = FakeModel([
        _parallel_tool_turn([
            ("c1", "read_file", {"path": "a.txt"}, "读 a"),
            ("c2", "read_file", {"path": "../escape.txt"}, "越界读"),
        ]),
        _answer("recovered"),
    ])

    result = await _runner(tmp_path, model).run("read", ["read_file"], _limits())

    assert result.answer == "recovered"
    items = model.requests[1].input_items
    outputs = [i for i in items if i.get("type") == "function_call_output"]
    assert len(outputs) == 2
    assert "alpha" in outputs[0]["output"]
    assert outputs[1]["call_id"] == "c2"
    assert "escape" in outputs[1]["output"]


@pytest.mark.asyncio
async def test_parallel_tool_calls_emit_tool_events_per_call(tmp_path):
    (tmp_path / "a.txt").write_text("alpha", encoding="utf-8")
    (tmp_path / "b.txt").write_text("beta", encoding="utf-8")
    model = FakeModel([
        _parallel_tool_turn([
            ("c1", "read_file", {"path": "a.txt"}, "读 a"),
            ("c2", "read_file", {"path": "b.txt"}, "读 b"),
        ]),
        _answer("done"),
    ])
    events = []

    await _runner(tmp_path, model).run(
        "read", ["read_file"], _limits(), on_event=events.append
    )

    starts = [e for e in events if e["kind"] == "tool_start"]
    steps = [e for e in events if e["kind"] == "tool_step"]
    summaries = [e for e in events if e["kind"] == "summary"]
    assert [e["tool"] for e in starts] == ["read_file", "read_file"]
    assert [e["call_id"] for e in starts] == ["c1", "c2"]
    assert len(steps) == 2 and all(e["ok"] for e in steps)
    assert [e["text"] for e in summaries] == ["读 a", "读 b"]
    assert [e["call_id"] for e in summaries] == ["c1", "c2"]
    # 并发语义：所有 tool_start 先于任何 tool_step（同一批并行调用的进度状态同时呈现）
    kinds = [e["kind"] for e in events]
    assert kinds.index("tool_step") > kinds.index("tool_start")
    assert kinds[:kinds.index("tool_step")].count("tool_start") == 2


@pytest.mark.asyncio
async def test_parallel_tool_calls_execute_concurrently(tmp_path):
    both_entered = asyncio.Event()
    counter = 0
    lock = asyncio.Lock()

    async def barrier(workspace, args):
        # 两个调用都进入后才放行：顺序执行会死锁等待，只有并发执行能完成
        nonlocal counter
        async with lock:
            counter += 1
            if counter >= 2:
                both_entered.set()
        await both_entered.wait()
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
        handler=barrier,
    )
    model = FakeModel([
        _parallel_tool_turn([
            ("c1", "echo", {"value": "x"}, "并行一"),
            ("c2", "echo", {"value": "y"}, "并行二"),
        ]),
        _answer("done"),
    ])

    result = await asyncio.wait_for(
        _runner(tmp_path, model, [spec]).run("task", ["echo"], _limits()),
        timeout=3,
    )

    assert result.answer == "done"
    items = model.requests[1].input_items
    outputs = [i for i in items if i.get("type") == "function_call_output"]
    assert len(outputs) == 2


@pytest.mark.asyncio
async def test_write_tool_calls_execute_serially(tmp_path):
    order: list[str] = []

    async def write_handler(workspace, args):
        order.append(f"start:{args['name']}")
        await asyncio.sleep(0.05)
        order.append(f"finish:{args['name']}")
        return ToolResult(status="ok", observation=f"wrote {args['name']}")

    spec = ToolSpec(
        name="write_x",
        description="write",
        parameters={
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
            "additionalProperties": False,
        },
        handler=write_handler,
        mutates=True,
    )
    model = FakeModel([
        _parallel_tool_turn([
            ("c1", "write_x", {"name": "a"}, "写 a"),
            ("c2", "write_x", {"name": "b"}, "写 b"),
        ]),
        _answer("done"),
    ])

    result = await _runner(tmp_path, model, [spec]).run("write", ["write_x"], _limits())

    assert result.answer == "done"
    # 串行语义：第一个写入完成前第二个不得开始；并发实现会出现 start:start:finish:finish
    assert order == ["start:a", "finish:a", "start:b", "finish:b"]
    items = model.requests[1].input_items
    outputs = [i for i in items if i.get("type") == "function_call_output"]
    assert [i.get("call_id") for i in outputs] == ["c1", "c2"]


@pytest.mark.asyncio
async def test_mixed_batch_reads_parallel_and_writes_serial_keep_original_order(tmp_path):
    both_reads_entered = asyncio.Event()
    read_count = 0
    lock = asyncio.Lock()

    async def barrier_read(workspace, args):
        # 两个只读调用都进入后才放行：只读并行则完成，只读串行则死锁超时
        nonlocal read_count
        async with lock:
            read_count += 1
            if read_count >= 2:
                both_reads_entered.set()
        await both_reads_entered.wait()
        return ToolResult(status="ok", observation=f"read {args['path']}")

    write_events: list[str] = []

    async def write_handler(workspace, args):
        write_events.append(f"start:{args['name']}")
        await asyncio.sleep(0.05)
        write_events.append(f"finish:{args['name']}")
        return ToolResult(status="ok", observation=f"wrote {args['name']}")

    read_spec = ToolSpec(
        name="read_x",
        description="read",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        },
        handler=barrier_read,
    )
    write_spec = ToolSpec(
        name="write_x",
        description="write",
        parameters={
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
            "additionalProperties": False,
        },
        handler=write_handler,
        mutates=True,
    )
    model = FakeModel([
        _parallel_tool_turn([
            ("c1", "write_x", {"name": "a"}, "写 a"),
            ("c2", "read_x", {"path": "x"}, "读 x"),
            ("c3", "write_x", {"name": "b"}, "写 b"),
            ("c4", "read_x", {"path": "y"}, "读 y"),
        ]),
        _answer("done"),
    ])

    result = await asyncio.wait_for(
        _runner(tmp_path, model, [read_spec, write_spec]).run(
            "mixed", ["read_x", "write_x"], _limits()
        ),
        timeout=3,
    )

    assert result.answer == "done"
    # 写入工具即使与只读工具同批，也严格串行
    assert write_events == ["start:a", "finish:a", "start:b", "finish:b"]
    # 结果仍按模型发出的原顺序回传
    items = model.requests[1].input_items
    outputs = [i for i in items if i.get("type") == "function_call_output"]
    assert [i.get("call_id") for i in outputs] == ["c1", "c2", "c3", "c4"]
    assert all("read " in outputs[i]["output"] for i in (1, 3))


@pytest.mark.asyncio
async def test_summary_and_tool_start_are_emitted_before_tool_step(tmp_path):
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
    assert [event["kind"] for event in events[:3]] == [
        "summary", "tool_start", "tool_step",
    ]
    assert events[0]["text"] == "我先确认一下"
    assert events[1] == {
        "kind": "tool_start",
        "step": 1,
        "tool": "echo",
        "call_id": "call_1",
        "args": {"value": "x"},
    }


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
        # 超出单轮并行上限（MAX_PARALLEL_TOOL_CALLS=4）→ 协议错误
        ModelTurn(function_calls=[
            FunctionCall(f"c{i}", "read_file", {"path": f"x{i}"}, "run")
            for i in range(5)
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
async def test_usage_event_is_emitted_per_model_turn(tmp_path):
    first = TokenUsage(prompt_tokens=10, completion_tokens=2, thinking_tokens=3,
                       total_tokens=15, model="m")
    second = TokenUsage(prompt_tokens=20, completion_tokens=4, thinking_tokens=5,
                        total_tokens=29, model="m")
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    model = FakeModel([
        _tool("read_file", {"path": "a.txt"}, usage=first),
        _answer("done", usage=second),
    ])
    events = []

    result = await _runner(tmp_path, model).run(
        "read", ["read_file"], _limits(), on_event=events.append
    )

    assert [e for e in events if e["kind"] == "usage"] == [
        {"kind": "usage", "step": 1, "prompt_tokens": 10, "total_tokens": 15},
        {"kind": "usage", "step": 2, "prompt_tokens": 20, "total_tokens": 29},
    ]
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


# ---------- 阶段 1：token 预估与上下文压缩 ----------

from harness.runner import estimate_prompt_tokens
from harness.tools.generic.planning import UPDATE_PLAN_SPEC


def test_estimate_prompt_tokens_default_and_calibrated():
    # 无校准：默认系数 0.35 token/字符
    assert estimate_prompt_tokens(1000, 100, []) == 1035
    assert estimate_prompt_tokens(None, 100, []) is None
    # 有校准：按最近几轮真实 (chars, tokens) 比值
    assert estimate_prompt_tokens(1000, 100, [(100, 40)]) == 1040
    assert estimate_prompt_tokens(1000, 100, [(100, 40), (200, 80)]) == 1040


def _echo_spec(observations: dict[str, str], name: str = "echo"):
    from harness.tools.base import ToolSpec, ToolResult

    return ToolSpec(
        name=name,
        description=name,
        parameters={
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
            "additionalProperties": False,
        },
        handler=lambda workspace, args: ToolResult(
            status="ok", observation=observations.get(str(args.get("value", "")), "small-result")
        ),
    )


def _big_tool_turn(observation: str, call_id: str = "call_1", usage=None, tool_name: str = "echo"):
    turn = _tool(tool_name, {"value": "x"}, call_id=call_id, usage=usage)
    turn.response_items = [
        {"type": "reasoning", "id": f"r-{call_id}",
         "content": [{"type": "reasoning_text", "text": f"先思考 {call_id} 的步骤"}]},
        {"type": "function_call", "call_id": call_id, "name": tool_name,
         "arguments": '{"value": "x", "summary": "执行"}'},
    ]
    return turn


@pytest.mark.asyncio
async def test_context_compression_replaces_old_tool_outputs_and_reasoning(tmp_path):
    big = "BIG-OUTPUT-" + "x" * 100_000
    t1 = _big_tool_turn(big, call_id="call_1", usage=TokenUsage(prompt_tokens=20_000, total_tokens=20_000))
    t2 = _tool("echo", {"value": "y"}, call_id="call_2", summary="继续", usage=TokenUsage(prompt_tokens=90_000, total_tokens=90_000))
    model = FakeModel([t1, t2, _answer("done")])
    trace = TraceRecorder(tmp_path / "trace.jsonl", "compress-run")
    events = []

    await _runner(tmp_path, model, [_echo_spec({"x": big, "y": "small-result"})],
                  context_window=100_000, keep_recent_steps=1, compression_level=1).run(
        "task", ["echo"], _limits(), trace=trace, on_event=events.append
    )

    compressed = [e for e in events if e["kind"] == "context_compressed"]
    assert len(compressed) == 1
    assert compressed[0]["dropped_steps"] == [1]
    assert compressed[0]["freed_tokens"] > 0

    third_items = model.requests[2].input_items
    assert third_items[-1]["type"] == "function_call_output"  # 最近一步（step 2）完整保留
    assert third_items[-1]["call_id"] == "call_2"
    outputs = [i.get("output", "") for i in third_items if i.get("type") == "function_call_output"]
    # 更早（step 1）的工具结果被占位说明替换
    assert all(big not in out for out in outputs)
    assert any("压缩" in out for out in outputs)
    # step 1 的 reasoning 被丢弃
    assert not any("先思考 call_1" in str(i) for i in third_items)
    # trace 记录压缩事件
    assert any(e["event"] == "context_compressed" for e in _events(trace))


@pytest.mark.asyncio
async def test_update_plan_output_is_never_compressed(tmp_path):
    big1 = "ECHO-OLD-" + "x" * 100_000
    big3 = "ECHO-RECENT-" + "z" * 50_000
    t1 = _tool("echo", {"value": "x"}, call_id="call_1", usage=TokenUsage(prompt_tokens=20_000, total_tokens=20_000))
    t2 = _tool("update_plan", {"steps": [{"step": "先调研", "status": "in_progress"}]},
               call_id="call_plan", usage=TokenUsage(prompt_tokens=60_000, total_tokens=60_000))
    t3 = _tool("echo", {"value": "z"}, call_id="call_3", summary="继续",
               usage=TokenUsage(prompt_tokens=95_000, total_tokens=95_000))
    model = FakeModel([t1, t2, t3, _answer("done")])
    tools = ToolRuntime(tmp_path, [UPDATE_PLAN_SPEC, _echo_spec({"x": big1, "z": big3})])

    await AgentRunner(
        model, tools, PROMPT, instructions="system", context_window=100_000, keep_recent_steps=1
    ).run("task", ["update_plan", "echo"], _limits())

    fourth_items = model.requests[-1].input_items
    serialized = json.dumps(fourth_items, ensure_ascii=False)
    # 更早步骤的 update_plan call + output 保留（plan 是任务级状态，永不压缩）
    assert "update_plan" in serialized
    assert "## 当前计划" in serialized
    # 更早步骤的 echo 工具结果被压缩掉；最近一步（step 3）完整保留
    assert big1 not in serialized
    assert big3 in serialized


@pytest.mark.asyncio
async def test_context_compression_keeps_two_recent_steps(tmp_path):
    big1 = "ECHO-STEP1-" + "x" * 100_000
    t1 = _tool("echo", {"value": "x"}, call_id="call_1", usage=TokenUsage(prompt_tokens=20_000, total_tokens=20_000))
    t2 = _tool("echo", {"value": "y"}, call_id="call_2", summary="继续", usage=TokenUsage(prompt_tokens=50_000, total_tokens=50_000))
    t3 = _tool("echo", {"value": "z"}, call_id="call_3", summary="继续", usage=TokenUsage(prompt_tokens=90_000, total_tokens=90_000))
    model = FakeModel([t1, t2, t3, _answer("done")])
    events = []

    await _runner(tmp_path, model, [_echo_spec({"x": big1, "y": "m2", "z": "m3"})],
                  context_window=100_000, keep_recent_steps=2).run(
        "task", ["echo"], _limits(), on_event=events.append
    )

    compressed = [e for e in events if e["kind"] == "context_compressed"]
    assert len(compressed) == 1
    assert compressed[0]["dropped_steps"] == [1]
    fourth_items = model.requests[-1].input_items
    serialized = json.dumps(fourth_items, ensure_ascii=False)
    # 最近两步（step 2/3）完整保留，仅 step 1 被压缩
    assert big1 not in serialized
    assert "m2" in serialized and "m3" in serialized


@pytest.mark.asyncio
async def test_context_compression_disabled_by_default(tmp_path):
    big = "BIG-OUTPUT-" + "x" * 100_000
    t1 = _tool("echo", {"value": "x"}, call_id="call_1", usage=TokenUsage(prompt_tokens=20_000, total_tokens=20_000))
    t2 = _tool("echo", {"value": "y"}, call_id="call_2", usage=TokenUsage(prompt_tokens=100_000, total_tokens=100_000))
    model = FakeModel([t1, t2, _answer("done")])
    events = []

    await _runner(tmp_path, model, [_echo_spec({"x": big, "y": big})]).run(
        "task", ["echo"], _limits(), on_event=events.append
    )

    assert not [e for e in events if e["kind"] == "context_compressed"]
    serialized = json.dumps(model.requests[2].input_items, ensure_ascii=False)
    assert big in serialized  # 未开启压缩：内容与 baseline 一致


@pytest.mark.asyncio
async def test_context_compression_zero_behavior_below_threshold(tmp_path):
    t1 = _tool("echo", {"value": "x"}, call_id="call_1", usage=TokenUsage(prompt_tokens=2_000, total_tokens=2_000))
    t2 = _tool("echo", {"value": "y"}, call_id="call_2", usage=TokenUsage(prompt_tokens=4_000, total_tokens=4_000))
    model = FakeModel([t1, t2, _answer("done")])
    trace = TraceRecorder(tmp_path / "trace.jsonl", "no-compress-run")
    events = []

    await _runner(tmp_path, model, [_echo_spec({"x": "small"})], context_window=100_000).run(
        "task", ["echo"], _limits(), trace=trace, on_event=events.append
    )

    assert not [e for e in events if e["kind"] == "context_compressed"]
    assert not any(e["event"] == "context_compressed" for e in _events(trace))


@pytest.mark.asyncio
async def test_context_compression_fallback_drops_old_assistant_messages(tmp_path):
    big = "TOOL-" + "x" * 10_000
    msg = "MESSAGE-" + "y" * 50_000
    t1 = _tool("echo", {"value": "x"}, call_id="call_1", usage=TokenUsage(prompt_tokens=20_000, total_tokens=20_000))
    t1.response_items = [
        {"type": "message", "role": "assistant", "id": "m1",
         "content": [{"type": "output_text", "text": msg}]},
        {"type": "function_call", "call_id": "call_1", "name": "echo",
         "arguments": '{"value": "x", "summary": "执行"}'},
    ]
    t2 = _tool("echo", {"value": "y"}, call_id="call_2", usage=TokenUsage(prompt_tokens=100_000, total_tokens=100_000))
    model = FakeModel([t1, t2, _answer("done")])
    events = []

    await _runner(tmp_path, model, [_echo_spec({"x": big, "y": "small"})],
                  context_window=100_000, compression_level=1).run(
        "task", ["echo"], _limits(), on_event=events.append
    )

    compressed = [e for e in events if e["kind"] == "context_compressed"]
    assert len(compressed) == 1
    assert compressed[0]["dropped_steps"] == [1]
    third_items = model.requests[-1].input_items
    serialized = json.dumps(third_items, ensure_ascii=False)
    # 兜底：更早的 assistant 消息与 tool output 都被丢弃
    assert msg not in serialized
    assert big not in serialized
    # 协议结构完整：call 与 output 仍成对（call_id 保留）
    call_ids = [i.get("call_id") for i in third_items
                if i.get("type") in ("function_call", "function_call_output")]
    assert call_ids.count("call_1") == 2 and call_ids.count("call_2") == 2
    # 最近一步完整保留
    assert "small" in serialized


@pytest.mark.asyncio
async def test_context_compression_multi_round_does_not_recount_placeholders(tmp_path):
    """连续多轮压缩：已占位的 tool output 不被再次替换/重复计入 dropped_steps。"""
    bigs = {f"k{i}": f"BIG-{i}-" + "x" * 80_000 for i in range(1, 6)}
    turns = []
    for i, pt in enumerate([25_000, 40_000, 55_000, 55_000, 55_000], start=1):
        raw = json.dumps({"value": f"k{i}", "summary": "执行"}, ensure_ascii=False)
        turns.append(ModelTurn(
            function_calls=[FunctionCall(f"call_{i}", "echo", {"value": f"k{i}"}, "执行", raw)],
            usage=TokenUsage(prompt_tokens=pt, total_tokens=pt),
            response_id=f"resp_call_{i}",
            response_items=[
                {"type": "reasoning", "id": f"r-{i}",
                 "content": [{"type": "reasoning_text", "text": f"先思考 {i}"}]},
                {"type": "function_call", "call_id": f"call_{i}", "name": "echo", "arguments": raw},
            ],
        ))
    turns.append(_answer("done"))
    model = FakeModel(turns)
    events = []

    await _runner(tmp_path, model, [_echo_spec(bigs)],
                  context_window=60_000, keep_recent_steps=1, compression_level=1).run(
        "task", ["echo"], _limits(max_steps=10), on_event=events.append
    )

    comps = [e for e in events if e["kind"] == "context_compressed"]
    assert len(comps) >= 3  # 连续多轮真实触发

    # 每个 step 最多出现两次：一次丢 reasoning、一次替换 tool output；不得随轮次膨胀
    counts: dict[int, int] = {}
    for c in comps:
        for st in c["dropped_steps"]:
            counts[st] = counts.get(st, 0) + 1
    assert max(counts.values()) <= 2, counts

    # 已占位的 output 不被再次替换：每个 step 的占位文本唯一，token 估算不反复重算
    seen: dict[str, set[str]] = {}
    for req in model.requests:
        for item in req.input_items:
            if item.get("type") == "function_call_output" and "上下文压缩" in item.get("output", ""):
                step_no = item["output"].split("第")[1].split(" 步")[0]
                seen.setdefault(step_no, set()).add(item["output"])
    assert all(len(texts) == 1 for texts in seen.values()), {k: len(v) for k, v in seen.items()}


@pytest.mark.asyncio
async def test_context_compression_level2_summarizes_old_steps(tmp_path):
    """level=2（默认）：第 1 级丢低价值内容后仍超软线 → LLM 摘要最早可压缩步骤，
    整步替换为摘要消息（协议结构完整、无悬空 call_id），并记录 context_summarized。"""
    big = "BIG-OUTPUT-" + "x" * 100_000
    t1 = _big_tool_turn(big, call_id="call_1", usage=TokenUsage(prompt_tokens=20_000, total_tokens=20_000))
    t2 = _tool("echo", {"value": "y"}, call_id="call_2", summary="继续",
               usage=TokenUsage(prompt_tokens=90_000, total_tokens=90_000))
    model = FakeModel([t1, t2, _answer("done")], summary_text="旧步骤摘要：已读取文件 A，得到关键数据 123。")
    trace = TraceRecorder(tmp_path / "trace.jsonl", "level2-summary")
    events = []

    await _runner(tmp_path, model, [_echo_spec({"x": big, "y": "small-result"})],
                  context_window=100_000, keep_recent_steps=1).run(
        "task", ["echo"], _limits(), trace=trace, on_event=events.append
    )

    # 发生一次独立的摘要调用（无工具、无 instructions），且看到了原始 tool output
    assert len(model.summary_requests) == 1
    summary_input = model.summary_requests[0].input_items[0]["content"]
    assert "上下文压缩" in summary_input
    assert big in summary_input

    compressed = [e for e in events if e["kind"] == "context_compressed"]
    assert len(compressed) == 1
    assert compressed[0]["dropped_steps"] == [1]
    assert compressed[0]["level"] == 2
    assert "summarize" in compressed[0]["chain"]
    assert compressed[0]["mode"] == "drop+summarize"  # 第 1 级丢了 reasoning，第 2 级摘要

    final = model.requests[-1].input_items
    serialized = json.dumps(final, ensure_ascii=False)
    assert "旧步骤摘要" in serialized          # 摘要消息进入后续上下文
    assert big not in serialized               # 覆盖步骤整步移除
    assert "先思考 call_1" not in serialized   # reasoning 第 1 级已丢
    call_ids = [i.get("call_id") for i in final
                if i.get("type") in ("function_call", "function_call_output")]
    assert "call_1" not in call_ids            # 无悬空 call_id
    assert call_ids.count("call_2") == 2       # 最近一步完整保留
    assert "small-result" in serialized
    assert any(e["event"] == "context_summarized" for e in _events(trace))
    ctx = [e for e in _events(trace) if e["event"] == "context_compressed"][0]
    assert ctx["data"]["compression_level"] == 2
    assert ctx["data"]["summary_covered"] == [1]


@pytest.mark.asyncio
async def test_context_compression_level2_summary_failure_degrades_to_placeholder(tmp_path):
    """level=2：摘要调用失败 → 降级为占位挖空（degraded），仍释放 token、协议结构完整，
    run 正常完成。"""
    big = "BIG-OUTPUT-" + "x" * 100_000
    t1 = _big_tool_turn(big, call_id="call_1", usage=TokenUsage(prompt_tokens=20_000, total_tokens=20_000))
    t2 = _tool("echo", {"value": "y"}, call_id="call_2", summary="继续",
               usage=TokenUsage(prompt_tokens=90_000, total_tokens=90_000))
    model = FakeModel([t1, t2, _answer("done")], summary_error=RuntimeError("summary provider down"))
    events = []

    result = await _runner(tmp_path, model, [_echo_spec({"x": big, "y": "small"})],
                           context_window=100_000, keep_recent_steps=1).run(
        "task", ["echo"], _limits(), on_event=events.append
    )

    assert result.finish_reason == "completed"
    assert len(model.summary_requests) == 1  # 摘要确实被尝试
    compressed = [e for e in events if e["kind"] == "context_compressed"]
    assert compressed and "degraded" in compressed[0]["chain"]
    assert compressed[0]["degraded"] is True
    serialized = json.dumps(model.requests[-1].input_items, ensure_ascii=False)
    assert big not in serialized
    assert "上下文压缩" in serialized  # 降级占位
    call_ids = [i.get("call_id") for i in model.requests[-1].input_items
                if i.get("type") in ("function_call", "function_call_output")]
    assert call_ids.count("call_1") == 2 and call_ids.count("call_2") == 2


@pytest.mark.asyncio
async def test_context_compression_level2_skips_summary_when_drop_suffices(tmp_path):
    """level=2：第 1 级低价值丢弃（超大 reasoning）已达标 → 不触发摘要调用，零成本解决。"""
    raw = json.dumps({"value": "x", "summary": "执行"}, ensure_ascii=False)
    t1 = ModelTurn(
        function_calls=[FunctionCall("call_1", "echo", {"value": "x"}, "执行", raw)],
        usage=TokenUsage(prompt_tokens=20_000, total_tokens=20_000),
        response_id="resp_call_1",
        response_items=[
            {"type": "reasoning", "id": "r-1",
             "content": [{"type": "reasoning_text", "text": "先思考" + "y" * 100_000}]},
            {"type": "function_call", "call_id": "call_1", "name": "echo", "arguments": raw},
        ],
    )
    t2 = _tool("echo", {"value": "y"}, call_id="call_2", summary="继续",
               usage=TokenUsage(prompt_tokens=90_000, total_tokens=90_000))
    model = FakeModel([t1, t2, _answer("done")])
    events = []

    result = await _runner(tmp_path, model, [_echo_spec({"x": "ok", "y": "small"})],
                           context_window=100_000, keep_recent_steps=1).run(
        "task", ["echo"], _limits(), on_event=events.append
    )

    assert result.finish_reason == "completed"
    assert model.summary_requests == []  # 第 1 级已达标，未付 LLM 成本
    compressed = [e for e in events if e["kind"] == "context_compressed"]
    assert compressed and compressed[0]["chain"] == ["drop"]
    serialized = json.dumps(model.requests[-1].input_items, ensure_ascii=False)
    assert "先思考" not in serialized  # 超大 reasoning 被丢弃
    assert "ok" in serialized          # 工具结果保留（低价值丢弃不碰高价值内容）


@pytest.mark.asyncio
async def test_context_compression_level2_existing_summary_is_not_resummarized(tmp_path):
    """level=2 连续多轮压缩：已生成的摘要消息不被再次覆盖/摘要，原摘要文本保持原样。"""
    bigs = {f"k{i}": f"BIG-{i}-" + "x" * 20_000 for i in range(1, 6)}
    turns = []
    for i, pt in enumerate([15_000, 25_000, 35_000, 42_000, 45_000], start=1):
        raw = json.dumps({"value": f"k{i}", "summary": "执行"}, ensure_ascii=False)
        turns.append(ModelTurn(
            function_calls=[FunctionCall(f"call_{i}", "echo", {"value": f"k{i}"}, "执行", raw)],
            usage=TokenUsage(prompt_tokens=pt, total_tokens=pt),
            response_id=f"resp_call_{i}",
            response_items=[
                {"type": "reasoning", "id": f"r-{i}",
                 "content": [{"type": "reasoning_text", "text": f"先思考 {i}"}]},
                {"type": "function_call", "call_id": f"call_{i}", "name": "echo", "arguments": raw},
            ],
        ))
    turns.append(_answer("done"))
    summary_text = "第一次摘要：关键事实 123 已记录。"
    model = FakeModel(turns, summary_text=summary_text)
    events = []

    await _runner(tmp_path, model, [_echo_spec(bigs)],
                  context_window=50_000, keep_recent_steps=1).run(
        "task", ["echo"], _limits(max_steps=10), on_event=events.append
    )

    assert len(model.summary_requests) >= 1
    serialized = json.dumps(model.requests[-1].input_items, ensure_ascii=False)
    # 第一次的摘要文本原样存活：后续压缩没有把它再覆盖
    assert summary_text in serialized
    assert serialized.count("⚠️ [上下文摘要] ") >= 1


@pytest.mark.asyncio
async def test_context_initial_estimate_blocks_over_hard_line(tmp_path):
    """开始时超硬线（0.95）：初始预估即超限 → 拦截，不发必败请求。"""
    model = FakeModel([_answer("done")])
    events = []
    trace = TraceRecorder(tmp_path / "trace.jsonl", "initial-over-hard")

    result = await _runner(tmp_path, model, context_window=300).run(
        "内容" + "x" * 1000, ["echo"], _limits(), trace=trace, on_event=events.append
    )

    assert result.finish_reason == "context_limit_exceeded"
    assert model.requests == []  # 初始拦截：零请求发出
    assert any(e["kind"] == "context_compressed" for e in events)
    assert any(e["event"] == "context_limit_exceeded" for e in _events(trace))


@pytest.mark.asyncio
async def test_context_initial_estimate_soft_only_no_block(tmp_path):
    """开始时超软线（0.9）但未超硬线（0.95）：记录触发、不拦截，正常提交。"""
    model = FakeModel([_answer("done")])
    trace = TraceRecorder(tmp_path / "trace.jsonl", "initial-soft")

    result = await _runner(tmp_path, model, context_window=150).run(
        "内容" + "x" * 300, ["echo"], _limits(), trace=trace
    )

    assert result.finish_reason == "completed"
    assert len(model.requests) == 1  # 软线区间（0.9~0.95）：无可压缩，直接提交
    compressed = [e for e in _events(trace) if e["event"] == "context_compressed"]
    assert compressed and compressed[0]["data"]["mode"] == "soft"
    assert compressed[0]["data"]["freed_tokens"] == 0


@pytest.mark.asyncio
async def test_context_hard_line_fifo_drops_oldest_turns(tmp_path):
    """硬线（0.95）：软线压缩后仍超 → 从最早 step 整轮 FIFO。update_plan 软线豁免，
    硬线可删整轮；step 0（当前用户轮次）与最近一步保留，协议结构完整。"""
    plan_steps = [{"step": "计划步骤" + "x" * 400, "status": "in_progress"} for _ in range(40)]
    t1 = _tool("update_plan", {"steps": plan_steps}, call_id="call_plan",
               usage=TokenUsage(prompt_tokens=96_000, total_tokens=96_000))
    t2 = _tool("echo", {"value": "y"}, call_id="call_2",
               usage=TokenUsage(prompt_tokens=96_000, total_tokens=96_000))
    model = FakeModel([t1, t2, _answer("done")])
    events = []

    await _runner(tmp_path, model, [UPDATE_PLAN_SPEC, _echo_spec({"y": "small"})],
                  context_window=100_000).run(
        "task", ["update_plan", "echo"], _limits(), on_event=events.append
    )

    comps = [e for e in events if e["kind"] == "context_compressed"]
    assert comps and comps[-1]["mode"] == "fifo"  # 软线挖不动（plan 豁免）→ 纯 FIFO
    assert comps[-1]["dropped_steps"] == [1]      # 整轮 FIFO：最早 step 全部删除
    third_items = model.requests[2].input_items
    serialized = json.dumps(third_items, ensure_ascii=False)
    # 整轮删除：update_plan 的 call 与 output 成对消失，无悬空 call_id
    assert "call_plan" not in serialized and "## 当前计划" not in serialized
    assert not any(i.get("type") in ("function_call", "function_call_output")
                   and i.get("call_id") == "call_plan" for i in third_items)
    # step 0（初始 user 消息）与最近一步（step 2）保留
    assert third_items[0]["role"] == "user"
    assert "call_2" in serialized and "small" in serialized


@pytest.mark.asyncio
async def test_parallel_tool_calls_tool_step_args_match_each_call(tmp_path):
    """并行工具调用时，每个 tool_step 事件必须携带自己那次调用的 args。

    回归：此前 tool_step 复用第一个循环残留的 args 变量，同一批所有事件
    都带上最后一个 call 的参数，导致前端 trace 面板把不同调用显示成同一调用。
    """
    (tmp_path / "a.txt").write_text("alpha", encoding="utf-8")
    (tmp_path / "b.txt").write_text("beta", encoding="utf-8")
    model = FakeModel([
        _parallel_tool_turn([
            ("c1", "read_file", {"path": "a.txt"}, "读 a"),
            ("c2", "read_file", {"path": "b.txt"}, "读 b"),
        ]),
        _answer("done"),
    ])
    events = []

    await _runner(tmp_path, model).run(
        "read", ["read_file"], _limits(), on_event=events.append
    )

    steps = [e for e in events if e["kind"] == "tool_step"]
    assert [e["call_id"] for e in steps] == ["c1", "c2"]
    assert [e["args"] for e in steps] == [
        {"path": "a.txt"},
        {"path": "b.txt"},
    ]
