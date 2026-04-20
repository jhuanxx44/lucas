import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient


def test_chat_endpoint_returns_sse():
    async def fake_stream(q):
        yield "event: status\ndata: {\"message\": \"testing\"}\n\n"
        yield "event: done\ndata: {\"total_tokens\": 0}\n\n"

    with patch("server.services.stream.chat_event_stream") as mock:
        mock.side_effect = fake_stream
        from server.app import create_app
        app = create_app()
        client = TestClient(app)
        resp = client.post("/api/chat", json={"question": "test"})
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        assert "event: status" in resp.text
        assert "event: done" in resp.text
