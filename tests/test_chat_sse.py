import json

import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from utils.token_tracker import TokenUsage


def _parse_sse(chunks: list[str]) -> list[tuple[str, dict]]:
    """把 SSE 原始块解析为 (event, data) 序列"""
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


# ---------- 路由层 ----------

def test_chat_endpoint_returns_sse():
    """路由层：验证 SSE content-type 和基本事件格式"""
    async def fake_stream(q, history=None, user_id="default"):
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


def test_chat_ignores_user_id_header():
    """单用户模式下，客户端请求头不能切换工作区。"""
    async def fake_stream(q, history=None, user_id="default"):
        assert user_id == "default"
        yield "event: done\ndata: {\"total_tokens\": 0}\n\n"

    with patch("server.routers.chat.chat_event_stream") as mock:
        mock.side_effect = fake_stream
        from server.app import create_app
        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/chat",
            headers={"X-User-Id": "another-user"},
            json={"question": "test"},
        )

        assert resp.status_code == 200


# ---------- agent_stream：AgentRunner → SSE 桥 ----------

class FakeModel:
    """按脚本依次返回固定响应；响应可以是 str 或 (str, TokenUsage) 元组"""

    def __init__(self, responses: list):
        self.responses = list(responses)
        self.prompts: list[str] = []

    async def complete(self, prompt: str):
        self.prompts.append(prompt)
        item = self.responses.pop(0)
        if isinstance(item, tuple):
            return item
        return item, None


async def _collect(question, history=None, model=None, workspace=None):
    from server.services.agent_stream import chat_event_stream
    chunks = []
    async for chunk in chat_event_stream(
        question, history, workspace=workspace, model_adapter=model,
    ):
        chunks.append(chunk)
    return _parse_sse(chunks)


async def test_agent_stream_full_event_sequence(tmp_path):
    """工具 step → answer 的完整事件序列与 total_tokens 累计"""
    u1 = TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150, model="m")
    u2 = TokenUsage(prompt_tokens=200, completion_tokens=80, total_tokens=280, model="m")
    model = FakeModel([
        (json.dumps({"action": "tool", "tool": "wiki_recall",
                     "args": {"query": "贵州茅台"}}), u1),
        (json.dumps({"action": "answer", "reply": "最终答案"}), u2),
    ])
    events = await _collect("查一下茅台", model=model, workspace=tmp_path)

    assert [e for e, _ in events] == [
        "researcher_start", "status", "synthesis_chunk", "researcher_done", "done",
    ]
    assert events[0][1] == {"id": "single", "name": "Lucas"}
    assert "wiki_recall" in events[1][1]["message"]
    assert "贵州茅台" in events[1][1]["message"]
    assert events[2][1] == {"text": "最终答案"}
    assert events[3][1] == {"id": "single"}
    assert events[4][1] == {"total_tokens": 430}


async def test_agent_stream_history_injected_into_instruction(tmp_path):
    """多轮历史被渲染进 instruction 文本"""
    model = FakeModel([json.dumps({"action": "answer", "reply": "ok"})])
    history = [
        {"role": "user", "content": "之前的问题"},
        {"role": "assistant", "content": "之前的回答"},
    ]
    events = await _collect("新问题", history=history, model=model, workspace=tmp_path)

    assert [e for e, _ in events] == [
        "researcher_start", "synthesis_chunk", "researcher_done", "done",
    ]
    prompt = model.prompts[0]
    assert "用户: 之前的问题" in prompt
    assert "助手: 之前的回答" in prompt
    assert "用户问题：新问题" in prompt
    assert events[-1][1] == {"total_tokens": 0}  # FakeModel 无 usage


async def test_agent_stream_model_exception_yields_error(tmp_path):
    """模型异常 → researcher_start 后跟 error 事件（中文友好文案）"""
    class BoomModel:
        async def complete(self, prompt: str):
            raise RuntimeError("boom")

    events = await _collect("test", model=BoomModel(), workspace=tmp_path)

    assert [e for e, _ in events] == ["researcher_start", "error"]
    assert "分析过程出错" in events[1][1]["message"]
    assert "boom" in events[1][1]["message"]


async def test_agent_stream_max_steps_yields_error(tmp_path):
    """始终调工具不作答 → max_steps → error 事件"""
    model = FakeModel([
        json.dumps({"action": "tool", "tool": "wiki_recall", "args": {"query": f"q{i}"}})
        for i in range(10)  # lucas.yaml single_agent.max_steps = 10
    ])
    events = await _collect("永不回答", model=model, workspace=tmp_path)

    kinds = [e for e, _ in events]
    assert kinds[0] == "researcher_start"
    assert kinds[-1] == "error"
    assert kinds.count("status") == 10
    assert "步骤达到上限" in events[-1][1]["message"]
