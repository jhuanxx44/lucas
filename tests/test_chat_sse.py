import asyncio
import json
from datetime import datetime

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
    visible_events = [item for item in events if item[0] != "trace_event"]

    assert [e for e, _ in visible_events] == [
        "dispatch", "researcher_start", "tool_step", "synthesis_chunk", "researcher_done", "done",
    ]
    assert visible_events[0][1] == {"researchers": [{"id": "single", "name": "Lucas"}], "mode": "single"}
    assert visible_events[1][1] == {"id": "single", "name": "Lucas"}
    assert visible_events[2][1] == {
        "step": 1,
        "tool": "wiki_recall",
        "args": {"query": "贵州茅台"},
        "ok": True,
        "output": "[wiki_recall] status=ok\n（wiki 知识库为空，没有可召回的页面）",
        "message": "Lucas 调用 wiki_recall: 贵州茅台",
    }
    assert visible_events[3][1] == {"text": "最终答案"}
    assert visible_events[4][1] == {"id": "single"}
    assert visible_events[5][1] == {"total_tokens": 430}


async def test_agent_stream_exports_complete_model_trajectory(tmp_path):
    """隐藏 trace 流包含每轮模型输入、原始输出，供导出完整复盘。"""
    tool_output = json.dumps({
        "summary": "先查知识库",
        "action": "tool",
        "tool": "wiki_recall",
        "args": {"query": "贵州茅台"},
    }, ensure_ascii=False)
    answer_output = json.dumps({
        "summary": "根据检索结果回答",
        "action": "answer",
        "reply": "最终答案",
    }, ensure_ascii=False)
    model = FakeModel([tool_output, answer_output])

    events = await _collect("查一下茅台", model=model, workspace=tmp_path)

    trace_events = [data for event, data in events if event == "trace_event"]
    assert [event["event"] for event in trace_events] == [
        "run_config", "model_input", "model_output", "model_input", "model_output",
    ]
    assert trace_events[0]["data"]["allowed_tools"]
    assert trace_events[1]["step"] == 1
    assert "用户问题：查一下茅台" in trace_events[1]["data"]["prompt"]
    assert trace_events[2] == {
        "event": "model_output",
        "step": 1,
        "data": {"output": tool_output},
    }
    assert "[wiki_recall] status=ok" in trace_events[3]["data"]["prompt"]
    assert trace_events[4]["data"]["output"] == answer_output


async def test_agent_stream_exports_provider_reasoning_without_display_event(tmp_path):
    """provider 返回的 reasoning 进入隐藏 trace，但不改变右侧展示事件。"""
    class ReasoningModel:
        async def complete_stream(self, prompt: str):
            yield "reasoning", "先判断知识库是否足够。"
            yield "content", json.dumps({"action": "answer", "reply": "够了"}, ensure_ascii=False)

    events = await _collect("资料够吗", model=ReasoningModel(), workspace=tmp_path)

    reasoning = [
        data for event, data in events
        if event == "trace_event" and data["event"] == "model_reasoning"
    ]
    assert reasoning == [{
        "event": "model_reasoning",
        "step": 1,
        "data": {"text": "先判断知识库是否足够。"},
    }]
    assert "thought" not in [event for event, _ in events]


async def test_agent_stream_dispatch_contract(tmp_path):
    """契约锁定：dispatch 先于 researcher_start，payload 含 researchers + mode=single。

    前端 useChat.ts 依赖 dispatch 触发 onResearchTarget（wiki 联动）。
    """
    model = FakeModel([json.dumps({"action": "answer", "reply": "ok"})])
    events = await _collect("问题", model=model, workspace=tmp_path)

    assert events[0][0] == "dispatch"
    assert events[0][1] == {
        "researchers": [{"id": "single", "name": "Lucas"}],
        "mode": "single",
    }
    assert events[1][0] == "researcher_start"


async def test_agent_stream_history_injected_into_instruction(tmp_path):
    """多轮历史被渲染进 instruction 文本"""
    model = FakeModel([json.dumps({"action": "answer", "reply": "ok"})])
    history = [
        {"role": "user", "content": "之前的问题"},
        {"role": "assistant", "content": "之前的回答"},
    ]
    events = await _collect("新问题", history=history, model=model, workspace=tmp_path)
    visible_events = [item for item in events if item[0] != "trace_event"]

    assert [e for e, _ in visible_events] == [
        "dispatch", "researcher_start", "synthesis_chunk", "researcher_done", "done",
    ]
    prompt = model.prompts[0]
    assert "用户: 之前的问题" in prompt
    assert "助手: 之前的回答" in prompt
    assert "用户问题：新问题" in prompt
    # 当前日期由代码注入（模型训练截止会误判年份）
    assert f"当前日期：{datetime.now():%Y-%m-%d}" in prompt
    assert visible_events[-1][1] == {"total_tokens": 0}  # FakeModel 无 usage


async def test_agent_stream_model_exception_yields_error(tmp_path):
    """模型异常 → researcher_start 后跟 error 事件（中文友好文案）"""
    class BoomModel:
        async def complete(self, prompt: str):
            raise RuntimeError("boom")

    events = await _collect("test", model=BoomModel(), workspace=tmp_path)
    visible_events = [item for item in events if item[0] != "trace_event"]

    assert [e for e, _ in visible_events] == ["dispatch", "researcher_start", "error"]
    assert visible_events[2][1]["message"] == "分析过程出错，请稍后重试。"
    # 内部异常详情（含 provider 英文报错）不外抛给前端
    assert "boom" not in visible_events[2][1]["message"]


async def test_agent_stream_max_steps_yields_error(tmp_path):
    """始终调工具不作答 → max_steps → error 事件"""
    model = FakeModel([
        json.dumps({"action": "tool", "tool": "wiki_recall", "args": {"query": f"q{i}"}})
        for i in range(10)  # lucas.yaml single_agent.max_steps = 10
    ])
    events = await _collect("永不回答", model=model, workspace=tmp_path)

    kinds = [e for e, _ in events]
    assert kinds[0] == "dispatch"
    assert kinds[1] == "researcher_start"
    assert kinds[-1] == "error"
    assert kinds.count("tool_step") == 10
    assert "步骤达到上限" in events[-1][1]["message"]


async def test_agent_stream_client_disconnect_cancels_run(tmp_path):
    """客户端断开（SSE generator 提前关闭）→ run_task 被取消，不再继续烧 token"""
    cancelled = asyncio.Event()

    class HangingModel:
        async def complete(self, prompt: str):
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                cancelled.set()
                raise
            return json.dumps({"action": "answer", "reply": "x"}), None

    from server.services.agent_stream import chat_event_stream
    gen = chat_event_stream("问题", workspace=tmp_path, model_adapter=HangingModel())
    first = await gen.__anext__()
    assert "event: dispatch" in first
    await asyncio.sleep(0.05)  # 让 run_task 进入挂起的模型调用
    await gen.aclose()
    await asyncio.sleep(0.01)  # 让取消传播到挂起的模型调用
    assert cancelled.is_set()


def test_error_message_timeout_friendly():
    """finish_reason=timeout → 中文文案"""
    from harness.models import AgentResult
    from server.services.agent_stream import _error_message
    msg = _error_message(AgentResult(finish_reason="timeout", error="elapsed 121s"))
    assert "超时" in msg


def test_error_message_hides_internal_english():
    """内部英文错误（如 repeated failing tool call aborted）不原样抛给用户"""
    from harness.models import AgentResult
    from server.services.agent_stream import _error_message
    msg = _error_message(AgentResult(
        finish_reason="error", error="repeated failing tool call aborted: read_file"))
    assert "repeated" not in msg
    assert "中断" in msg
