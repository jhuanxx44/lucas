"""Native Responses streaming behavior at the AgentRunner boundary."""

import json

import pytest

from harness.models import FunctionCall, ModelEvent, ModelTurn, RunLimits
from harness.runner import AgentRunner
from harness.tools.generic.filesystem import READ_FILE_SPEC
from harness.tools.registry import ToolRuntime
from utils.token_tracker import TokenUsage


PROMPT = "任务：{instruction}"


def _answer(text="done", response_id="answer"):
    return ModelTurn(
        output_text=text,
        response_id=response_id,
        response_items=[{"type": "message", "id": response_id, "content": text}],
    )


def _tool(path="a.txt", call_id="call_1"):
    raw = json.dumps({"path": path, "summary": "先读取文件"}, ensure_ascii=False)
    return ModelTurn(
        function_calls=[FunctionCall(
            call_id=call_id,
            name="read_file",
            arguments={"path": path},
            summary="先读取文件",
            raw_arguments=raw,
        )],
        response_id=f"resp_{call_id}",
        response_items=[{
            "type": "function_call",
            "call_id": call_id,
            "name": "read_file",
            "arguments": raw,
        }],
    )


class FakeStreamModel:
    def __init__(self, streams, fallbacks=None):
        self.streams = list(streams)
        self.fallbacks = list(fallbacks or [])
        self.requests = []

    async def complete_stream(self, request):
        self.requests.append(request)
        stream = self.streams.pop(0)
        if isinstance(stream, Exception):
            raise stream
        for event in stream:
            yield event

    async def complete(self, request):
        self.requests.append(request)
        return self.fallbacks.pop(0)


def _runner(tmp_path, model):
    return AgentRunner(
        model,
        ToolRuntime(tmp_path, [READ_FILE_SPEC]),
        PROMPT,
        instructions="system",
    )


@pytest.mark.asyncio
async def test_final_output_text_deltas_are_forwarded_after_completed_turn(tmp_path):
    turn = _answer("你好世界")
    turn.usage = TokenUsage(prompt_tokens=2, completion_tokens=2, total_tokens=4, model="m")
    model = FakeStreamModel([[
        ModelEvent(kind="reasoning_delta", text="先想"),
        ModelEvent(kind="output_text_delta", text="你好"),
        ModelEvent(kind="output_text_delta", text="世界"),
        ModelEvent(kind="completed", turn=turn),
    ]])
    events = []

    result = await _runner(tmp_path, model).run(
        "hello",
        [],
        RunLimits(max_steps=3, timeout_seconds=0),
        on_event=events.append,
        stream_answer=True,
    )

    assert result.answer == "你好世界"
    assert [(event["kind"], event.get("text")) for event in events[:-1]] == [
        ("thought", "先想"),
        ("answer_chunk", "你好"),
        ("answer_chunk", "世界"),
    ]
    assert events[-1]["kind"] == "answer"
    assert events[-1]["streamed_chars"] == 4
    assert result.usage.total_tokens == 4


@pytest.mark.asyncio
async def test_tool_turn_does_not_leak_buffered_output_text(tmp_path):
    (tmp_path / "a.txt").write_text("content", encoding="utf-8")
    tool_turn = _tool()
    answer_turn = _answer("完成")
    model = FakeStreamModel([
        [
            ModelEvent(kind="output_text_delta", text="不应展示"),
            ModelEvent(kind="completed", turn=tool_turn),
        ],
        [
            ModelEvent(kind="output_text_delta", text="完成"),
            ModelEvent(kind="completed", turn=answer_turn),
        ],
    ])
    events = []

    result = await _runner(tmp_path, model).run(
        "read",
        ["read_file"],
        RunLimits(max_steps=3, timeout_seconds=0),
        on_event=events.append,
        stream_answer=True,
    )

    chunks = [event["text"] for event in events if event["kind"] == "answer_chunk"]
    assert result.answer == "完成"
    assert chunks == ["完成"]
    assert "不应展示" not in "".join(chunks)
    assert any(event["kind"] == "summary" for event in events)
    assert any(event["kind"] == "tool_step" for event in events)


@pytest.mark.asyncio
async def test_final_stream_discards_commentary_deltas_not_in_normalized_answer(tmp_path):
    model = FakeStreamModel([[
        ModelEvent(kind="output_text_delta", text="先总结一下。"),
        ModelEvent(kind="output_text_delta", text="最终答案"),
        ModelEvent(kind="completed", turn=_answer("最终答案")),
    ]])
    events = []

    result = await _runner(tmp_path, model).run(
        "answer",
        [],
        RunLimits(max_steps=3, timeout_seconds=0),
        on_event=events.append,
        stream_answer=True,
    )

    chunks = [event["text"] for event in events if event["kind"] == "answer_chunk"]
    assert result.answer == "最终答案"
    assert "".join(chunks) == "最终答案"
    assert events[-1]["streamed_chars"] == len("最终答案")


@pytest.mark.asyncio
async def test_mixed_tool_and_final_text_is_corrected_without_stream_leak(tmp_path):
    mixed = _tool()
    mixed.output_text = "错误正文"
    model = FakeStreamModel([
        [
            ModelEvent(kind="output_text_delta", text="错误正文"),
            ModelEvent(kind="completed", turn=mixed),
        ],
        [
            ModelEvent(kind="output_text_delta", text="已修正"),
            ModelEvent(kind="completed", turn=_answer("已修正")),
        ],
    ])
    events = []

    result = await _runner(tmp_path, model).run(
        "task",
        ["read_file"],
        RunLimits(max_steps=3, timeout_seconds=0),
        on_event=events.append,
        stream_answer=True,
    )

    assert result.answer == "已修正"
    chunks = "".join(event["text"] for event in events if event["kind"] == "answer_chunk")
    assert chunks == "已修正"


@pytest.mark.asyncio
async def test_stream_transport_failure_falls_back_to_non_stream_response(tmp_path):
    model = FakeStreamModel([RuntimeError("stream disconnected")], [_answer("fallback")])
    events = []

    result = await _runner(tmp_path, model).run(
        "task",
        [],
        RunLimits(max_steps=3, timeout_seconds=0),
        on_event=events.append,
        stream_answer=True,
    )

    assert result.answer == "fallback"
    assert [event for event in events if event["kind"] == "answer_chunk"] == []
    assert events[-1]["kind"] == "answer"
    assert events[-1]["streamed_chars"] == 0


@pytest.mark.asyncio
async def test_stream_without_completed_event_falls_back(tmp_path):
    model = FakeStreamModel(
        [[ModelEvent(kind="output_text_delta", text="partial")]],
        [_answer("complete")],
    )

    result = await _runner(tmp_path, model).run(
        "task",
        [],
        RunLimits(max_steps=3, timeout_seconds=0),
        on_event=lambda event: None,
        stream_answer=True,
    )

    assert result.answer == "complete"
