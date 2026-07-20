"""Answer 阶段逐 token 流式：AnswerStreamParser 单测 + Runner / agent_stream 集成。

规划：docs/plans/2026-07-20-answer-streaming.md
"""
import json
from pathlib import Path

import pytest

from harness.models import RunLimits
from harness.runner import AgentRunner, load_prompt_template
from harness.streaming import AnswerStreamParser
from harness.trace import TraceRecorder, read_trace
from harness.tools.registry import ToolRuntime
from harness.tools.generic.filesystem import READ_FILE_SPEC

LIMITS = RunLimits(max_steps=5, timeout_seconds=30)
PROMPT = load_prompt_template(
    Path(__file__).resolve().parent.parent / "prompts" / "harness" / "tool-loop.md"
)


def _feed_all(parser: AnswerStreamParser, text: str, size: int = 3) -> list[str]:
    out = []
    for i in range(0, len(text), size):
        out.extend(parser.feed(text[i:i + size]))
    out.extend(parser.finalize())
    return out


# ---------- AnswerStreamParser ----------

def test_tool_call_no_chunks():
    raw = json.dumps({"action": "tool", "tool": "wiki_recall",
                      "args": {"query": "贵州茅台"}}, ensure_ascii=False)
    assert _feed_all(AnswerStreamParser(), raw) == []


def test_string_answer_chunks_join_to_reply():
    reply = "你好，世界！这是最终答案。"
    raw = json.dumps({"action": "answer", "reply": reply}, ensure_ascii=False)
    chunks = _feed_all(AnswerStreamParser(), raw)
    assert len(chunks) > 1
    assert "".join(chunks) == reply


def test_markdown_fence_prefix():
    reply = "围栏里的答案"
    raw = "```json\n" + json.dumps(
        {"action": "answer", "reply": reply}, ensure_ascii=False) + "\n```"
    assert "".join(_feed_all(AnswerStreamParser(), raw, size=2)) == reply


@pytest.mark.parametrize("size", [1, 2, 3, 5, 7])
def test_escapes_across_chunk_boundaries(size):
    # ensure_ascii=True → 中文/emoji 走 \uXXXX（emoji 为代理对），换行等走简单转义
    reply = '换行\n引号"反斜杠\\制表\temoji😀中文'
    raw = json.dumps({"action": "answer", "reply": reply})
    assert "\\u" in raw  # 确认确实覆盖了 \uXXXX 路径
    assert "".join(_feed_all(AnswerStreamParser(), raw, size=size)) == reply


def test_reply_before_action():
    raw = '{"reply": "先答", "action": "answer"}'
    assert "".join(_feed_all(AnswerStreamParser(), raw)) == "先答"


def test_non_string_reply_no_chunks():
    raw = json.dumps({"action": "answer", "reply": {"a": 1}})
    assert _feed_all(AnswerStreamParser(), raw) == []


def test_invalid_json_no_chunks():
    assert _feed_all(AnswerStreamParser(), "这不是 JSON") == []


def test_empty_stream():
    assert _feed_all(AnswerStreamParser(), "") == []


def test_bare_json_answer_no_chunks():
    # 宽容解析的无 action 外壳答案：不流式，由最终 answer 整段返回
    assert _feed_all(AnswerStreamParser(), '{"y2022": 2606, "y2023": 2891}') == []


# ---------- Runner 集成 ----------

class FakeStreamModel:
    """complete / complete_stream 双通道；响应可以是 str 或 Exception（模拟中途失败）"""

    def __init__(self, responses: list, chunk_size: int = 4):
        self.responses = list(responses)
        self.chunk_size = chunk_size
        self.prompts: list[str] = []

    async def complete(self, prompt: str):
        self.prompts.append(prompt)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item, None

    async def complete_stream(self, prompt: str):
        self.prompts.append(prompt)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        for i in range(0, len(item), self.chunk_size):
            yield item[i:i + self.chunk_size]


def _runner(tmp_path: Path, model) -> AgentRunner:
    return AgentRunner(model, ToolRuntime(tmp_path, [READ_FILE_SPEC]), PROMPT)


def _trace(tmp_path: Path) -> TraceRecorder:
    trace = TraceRecorder(tmp_path / "trace.jsonl", "run-test")
    trace.record("run_started")
    return trace


async def test_streaming_answer_emits_ordered_chunks(tmp_path):
    reply = "流式答案逐字到达，包含换行\n和引号\"测试"
    raw = json.dumps({"action": "answer", "reply": reply}, ensure_ascii=False)
    model = FakeStreamModel([raw], chunk_size=3)
    events: list[dict] = []
    result = await _runner(tmp_path, model).run(
        "t", ["read_file"], LIMITS, _trace(tmp_path),
        on_event=events.append, stream_answer=True,
    )

    assert result.finish_reason == "completed"
    assert result.answer == reply
    chunks = [e["text"] for e in events if e["kind"] == "answer_chunk"]
    assert len(chunks) > 1
    assert "".join(chunks) == reply
    answer_evt = next(e for e in events if e["kind"] == "answer")
    assert answer_evt["streamed_chars"] == len(reply)


async def test_streaming_tool_step_emits_no_chunks(tmp_path):
    """工具步骤经流式通道但解析器判定 BUFFER：只发 tool_step，不发 answer_chunk"""
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    model = FakeStreamModel([
        json.dumps({"action": "tool", "tool": "read_file", "args": {"path": "a.txt"}}),
        json.dumps({"action": "answer", "reply": "读完啦"}),
    ])
    events: list[dict] = []
    result = await _runner(tmp_path, model).run(
        "t", ["read_file"], LIMITS, _trace(tmp_path),
        on_event=events.append, stream_answer=True,
    )

    assert result.finish_reason == "completed"
    kinds = [e["kind"] for e in events]
    assert kinds[0] == "tool_step"
    assert "answer_chunk" in kinds
    # 工具 step 之前没有任何 answer_chunk
    assert kinds.index("tool_step") < kinds.index("answer_chunk")
    chunks = [e["text"] for e in events if e["kind"] == "answer_chunk"]
    assert "".join(chunks) == "读完啦"


async def test_stream_disabled_no_chunks(tmp_path):
    """stream_answer=False（默认，eval 路径）：即使 adapter 支持流式也不发 chunk"""
    model = FakeStreamModel([
        json.dumps({"action": "answer", "reply": "非流式"}),
    ])
    events: list[dict] = []
    result = await _runner(tmp_path, model).run(
        "t", ["read_file"], LIMITS, _trace(tmp_path), on_event=events.append,
    )

    assert result.answer == "非流式"
    assert [e["kind"] for e in events] == ["answer"]
    assert "streamed_chars" not in events[0]


async def test_stream_fallback_on_exception(tmp_path):
    """流式中途异常 → 记 trace 后回退 complete()，run 不中断"""
    reply = "回退后的答案"
    model = FakeStreamModel([
        RuntimeError("stream boom"),
        json.dumps({"action": "answer", "reply": reply}),
    ])
    events: list[dict] = []
    trace = _trace(tmp_path)
    result = await _runner(tmp_path, model).run(
        "t", ["read_file"], LIMITS, trace,
        on_event=events.append, stream_answer=True,
    )

    assert result.finish_reason == "completed"
    assert result.answer == reply
    fallback = [e for e in read_trace(trace.path)
                if e["event"] == "answer_stream_fallback"]
    assert len(fallback) == 1
    assert "stream boom" in fallback[0]["data"]["error"]


async def test_streaming_history_replay_identical(tmp_path):
    """流式路径的全量回放与非流式一字不差：下一轮 prompt 含模型原始输出"""
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
    first = json.dumps({"action": "tool", "tool": "read_file",
                        "args": {"path": "a.txt"}}, ensure_ascii=False)
    model = FakeStreamModel([first, json.dumps({"action": "answer", "reply": "done"})])
    await _runner(tmp_path, model).run(
        "t", ["read_file"], LIMITS, _trace(tmp_path),
        on_event=lambda e: None, stream_answer=True,
    )

    assert f"【你】{first}" in model.prompts[1]
    assert "【工具】[read_file] status=ok" in model.prompts[1]


# ---------- agent_stream 契约 ----------

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


async def _collect(question, model, workspace):
    from server.services.agent_stream import chat_event_stream
    chunks = []
    async for chunk in chat_event_stream(
        question, workspace=workspace, model_adapter=model,
    ):
        chunks.append(chunk)
    return _parse_sse(chunks)


async def test_agent_stream_incremental_synthesis_chunks(tmp_path):
    """多个 synthesis_chunk 依序到达，拼接 == 最终答案，无重复补尾"""
    reply = "流式答案逐字到达前端"
    model = FakeStreamModel(
        [json.dumps({"action": "answer", "reply": reply}, ensure_ascii=False)],
        chunk_size=3,
    )
    events = await _collect("问题", model, tmp_path)

    kinds = [e for e, _ in events]
    assert kinds[0] == "dispatch" and kinds[1] == "researcher_start"
    assert kinds[-2:] == ["researcher_done", "done"]
    chunks = [d["text"] for e, d in events if e == "synthesis_chunk"]
    assert len(chunks) > 1
    assert "".join(chunks) == reply
    # 流式无 usage：done 如实反映 0
    assert events[-1][1] == {"total_tokens": 0}


async def test_agent_stream_tool_step_then_streamed_answer(tmp_path):
    """结构化工具 step 先于 answer 的增量 chunk；工具步不产生 synthesis_chunk"""
    (tmp_path / "wiki").mkdir()
    model = FakeStreamModel([
        json.dumps({"action": "tool", "tool": "wiki_recall",
                    "args": {"query": "茅台"}}),
        json.dumps({"action": "answer", "reply": "答案在这里"}),
    ])
    events = await _collect("查一下", model, tmp_path)

    kinds = [e for e, _ in events]
    assert kinds.index("tool_step") < kinds.index("synthesis_chunk")
    assert kinds.count("tool_step") == 1
    chunks = [d["text"] for e, d in events if e == "synthesis_chunk"]
    assert "".join(chunks) == "答案在这里"


async def test_agent_stream_buffered_answer_tail_fill(tmp_path):
    """解析器保守缓冲（非字符串 reply）时整段补尾，一个字不缺"""
    raw = json.dumps({"action": "answer", "reply": {"y2022": 2606}})
    model = FakeStreamModel([raw])
    events = await _collect("结构化", model, tmp_path)

    chunks = [d["text"] for e, d in events if e == "synthesis_chunk"]
    assert len(chunks) == 1
    assert json.loads(chunks[0]) == {"y2022": 2606}
