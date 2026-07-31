import asyncio
import json
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from harness.models import FunctionCall, ModelEvent, ModelRequest, ModelTurn
from utils.token_tracker import TokenUsage


def _parse_sse(chunks: list[str]) -> list[tuple[str, dict]]:
    events = []
    for chunk in chunks:
        event = data = None
        for line in chunk.strip().splitlines():
            if line.startswith("event: "):
                event = line[len("event: "):]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: "):])
        events.append((event, data))
    return events


def _answer(text="最终答案", usage=None):
    return ModelTurn(
        output_text=text,
        usage=usage,
        response_id="resp_answer",
        response_items=[{"type": "message", "id": "m1", "content": text}],
    )


def _tool(name="wiki_recall", args=None, *, call_id="call_1", summary="先查一下资料", usage=None):
    args = args or {"query": "贵州茅台"}
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


def test_chat_endpoint_returns_sse():
    async def fake_stream(q, history=None, user_id="default", model_override=None):
        assert model_override is None
        yield "event: status\ndata: {\"message\": \"testing\"}\n\n"
        yield "event: done\ndata: {\"total_tokens\": 0}\n\n"

    with patch("server.routers.chat.chat_event_stream") as mock:
        mock.side_effect = fake_stream
        from server.app import create_app
        response = TestClient(create_app()).post("/api/chat", json={"question": "test"})

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    assert "event: done" in response.text


def test_chat_question_max_length():
    from server.app import create_app
    response = TestClient(create_app()).post("/api/chat", json={"question": "x" * 2001})
    assert response.status_code == 422


def test_chat_ignores_user_id_header():
    async def fake_stream(q, history=None, user_id="default", model_override=None):
        assert user_id == "default"
        yield "event: done\ndata: {\"total_tokens\": 0}\n\n"

    with patch("server.routers.chat.chat_event_stream") as mock:
        mock.side_effect = fake_stream
        from server.app import create_app
        response = TestClient(create_app()).post(
            "/api/chat",
            headers={"X-User-Id": "another-user"},
            json={"question": "test"},
        )
    assert response.status_code == 200


class FakeModel:
    def __init__(self, turns):
        self.turns = list(turns)
        self.requests: list[ModelRequest] = []

    async def complete(self, request: ModelRequest):
        self.requests.append(request)
        value = self.turns.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


async def _collect(question, history=None, model=None, workspace=None):
    from server.services.agent_stream import chat_event_stream
    chunks = []
    async for chunk in chat_event_stream(
        question, history, workspace=workspace, model_adapter=model,
    ):
        chunks.append(chunk)
    return _parse_sse(chunks)


@pytest.mark.asyncio
async def test_agent_stream_full_native_event_sequence(tmp_path):
    u1 = TokenUsage(prompt_tokens=100, completion_tokens=40, thinking_tokens=10,
                    total_tokens=150, model="m")
    u2 = TokenUsage(prompt_tokens=200, completion_tokens=60, thinking_tokens=20,
                    total_tokens=280, model="m")
    model = FakeModel([
        _tool(usage=u1),
        _answer(usage=u2),
    ])

    events = await _collect("查一下茅台", model=model, workspace=tmp_path)
    visible = [item for item in events if item[0] != "trace_event"]

    assert [name for name, _ in visible] == [
        "dispatch", "researcher_start", "summary", "tool_start", "tool_step",
        "synthesis_chunk", "researcher_done", "done",
    ]
    assert visible[2][1] == {"step": 1, "text": "先查一下资料"}
    assert visible[3][1]["tool"] == "wiki_recall"
    assert visible[3][1]["args"] == {"query": "贵州茅台"}
    assert visible[3][1]["message"] == "Lucas 调用 wiki_recall: 贵州茅台"
    assert visible[4][1]["ok"] is True
    assert visible[5][1] == {"text": "最终答案"}
    assert visible[-1][1] == {"total_tokens": 430}


@pytest.mark.asyncio
async def test_agent_stream_exports_native_model_trajectory(tmp_path):
    model = FakeModel([_tool(), _answer()])

    events = await _collect("查一下茅台", model=model, workspace=tmp_path)
    trace_events = [data for event, data in events if event == "trace_event"]
    names = [event["event"] for event in trace_events]

    assert names == [
        "run_started", "run_config",
        "model_input", "model_output", "model_input", "model_output",
        "assistant_answer", "run_finished",
    ]
    config = trace_events[1]["data"]
    assert config["protocol"] == "openai_responses"
    assert config["tools"]
    assert config["tools"][0]["type"] == "function"
    first_input = trace_events[2]["data"]["input"]
    assert "用户问题：查一下茅台" in first_input[0]["content"]
    assert trace_events[3]["data"]["items"][0]["type"] == "function_call"
    second_input = trace_events[4]["data"]["input"]
    assert second_input[-1]["type"] == "function_call_output"
    assert trace_events[-1]["data"]["finishReason"] == "completed"


@pytest.mark.asyncio
async def test_provider_reasoning_is_hidden_trace_not_visible_event(tmp_path):
    class ReasoningModel:
        async def complete_stream(self, request):
            yield ModelEvent(kind="reasoning_delta", text="先判断资料是否足够。")
            yield ModelEvent(kind="output_text_delta", text="够了")
            yield ModelEvent(kind="completed", turn=_answer("够了"))

    events = await _collect("资料够吗", model=ReasoningModel(), workspace=tmp_path)

    reasoning = [
        data for event, data in events
        if event == "trace_event" and data["event"] == "model_reasoning"
    ]
    assert reasoning == [{
        "event": "model_reasoning",
        "step": 1,
        "data": {"text": "先判断资料是否足够。"},
    }]
    assert "thought" not in [event for event, _ in events]


@pytest.mark.asyncio
async def test_history_and_date_are_in_initial_explicit_input(tmp_path):
    model = FakeModel([_answer("ok")])
    history = [
        {"role": "user", "content": "之前的问题"},
        {"role": "assistant", "content": "之前的回答"},
    ]

    await _collect("新问题", history=history, model=model, workspace=tmp_path)

    content = model.requests[0].input_items[0]["content"]
    assert "用户: 之前的问题" in content
    assert "助手: 之前的回答" in content
    assert "用户问题：新问题" in content
    assert f"当前日期：{datetime.now():%Y-%m-%d}" in content


@pytest.mark.asyncio
async def test_model_exception_yields_friendly_error(tmp_path):
    events = await _collect("test", model=FakeModel([RuntimeError("secret provider error")]),
                            workspace=tmp_path)
    visible = [item for item in events if item[0] != "trace_event"]

    assert [name for name, _ in visible] == ["dispatch", "researcher_start", "error"]
    assert visible[-1][1]["message"] == "分析过程出错，请稍后重试。"
    assert "secret" not in visible[-1][1]["message"]


@pytest.mark.asyncio
async def test_unlimited_steps_supports_multiple_native_calls(tmp_path):
    model = FakeModel([
        _tool(args={"query": "q1"}, call_id="c1"),
        _tool(args={"query": "q2"}, call_id="c2"),
        _tool(args={"query": "q3"}, call_id="c3"),
        _answer("分析完成"),
    ])

    events = await _collect("不限步数测试", model=model, workspace=tmp_path)
    names = [name for name, _ in events]

    assert names.count("tool_step") == 3
    assert names[-1] == "done"


@pytest.mark.asyncio
async def test_client_disconnect_cancels_native_model_call(tmp_path):
    cancelled = asyncio.Event()

    class HangingModel:
        async def complete(self, request):
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                cancelled.set()
                raise

    from server.services.agent_stream import chat_event_stream
    generator = chat_event_stream("问题", workspace=tmp_path, model_adapter=HangingModel())
    first = await generator.__anext__()
    assert "event: dispatch" in first
    await asyncio.sleep(0.05)
    await generator.aclose()
    await asyncio.sleep(0.01)
    assert cancelled.is_set()


def test_error_messages_hide_internal_details():
    from harness.models import AgentResult
    from server.services.agent_stream import _error_message

    assert "超时" in _error_message(AgentResult(finish_reason="timeout"))
    message = _error_message(AgentResult(finish_reason="protocol_error", error="secret"))
    assert "secret" not in message
    assert "中断" in message
