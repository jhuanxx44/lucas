import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient


def test_chat_endpoint_returns_sse():
    """路由层：验证 SSE content-type 和基本事件格式"""
    async def fake_stream(q, history=None):
        yield "event: status\ndata: {\"message\": \"testing\"}\n\n"
        yield "event: done\ndata: {\"total_tokens\": 0}\n\n"

    with patch("server.routers.chat.chat_event_stream") as mock:
        mock.side_effect = fake_stream
        from server.app import create_app
        app = create_app()
        client = TestClient(app)
        resp = client.post("/api/chat", json={"question": "test"})
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        assert "event: status" in resp.text
        assert "event: done" in resp.text


def test_chat_question_max_length():
    """验证 question 长度限制"""
    from server.app import create_app
    app = create_app()
    client = TestClient(app)
    resp = client.post("/api/chat", json={"question": "x" * 2001})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_chat_event_stream_passes_history():
    """stream.py：验证 history 被注入到 Manager memory"""
    mock_manager = MagicMock()
    mock_manager.memory = MagicMock()
    mock_manager.memory.add_turn = MagicMock()

    async def fake_analyze(q):
        yield {"event": "done", "data": {"total_tokens": 0}}

    mock_manager.analyze_stream = fake_analyze

    with patch("server.services.stream.load_config"), \
         patch("server.services.stream.Manager", return_value=mock_manager):
        from server.services.stream import chat_event_stream
        history = [
            {"role": "user", "content": "之前的问题"},
            {"role": "assistant", "content": "之前的回答"},
        ]
        events = []
        async for chunk in chat_event_stream("新问题", history):
            events.append(chunk)

        assert mock_manager.memory.add_turn.call_count == 2
        assert any("done" in e for e in events)


@pytest.mark.asyncio
async def test_chat_event_stream_catches_exception():
    """stream.py：验证异常被捕获并作为 error 事件返回"""
    with patch("server.services.stream.load_config", side_effect=RuntimeError("config broken")):
        from server.services.stream import chat_event_stream
        events = []
        async for chunk in chat_event_stream("test"):
            events.append(chunk)

        assert len(events) == 1
        assert "event: error" in events[0]
        assert "config broken" in events[0]
