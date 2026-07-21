import asyncio
import json
from pathlib import Path

import pytest

from harness.models import RunLimits
from harness.trace import TraceRecorder, read_trace
from harness.runner import AgentRunner, load_prompt_template
from harness.tools.base import ToolResult, ToolSpec
from harness.tools.generic.filesystem import (
    APPLY_PATCH_SPEC,
    LIST_FILES_SPEC,
    READ_FILE_SPEC,
    SEARCH_SPEC,
    WRITE_FILE_SPEC,
)
from harness.tools.registry import ToolRuntime
from utils.token_tracker import TokenUsage

LIMITS = RunLimits(max_steps=5, timeout_seconds=30)


class FakeModel:
    """按脚本依次返回固定响应；响应可以是 str 或 (str, TokenUsage) 元组"""

    def __init__(self, responses: list):
        self.responses = list(responses)
        self.prompts: list[str] = []

    async def complete(self, prompt: str) -> tuple[str, TokenUsage | None]:
        self.prompts.append(prompt)
        if self.responses:
            item = self.responses.pop(0)
            if isinstance(item, tuple):
                return item
            return item, None
        return json.dumps({"action": "answer", "reply": "fallback"}), None


def _runner(tmp_path: Path, model: FakeModel, trace: TraceRecorder, specs=None):
    tools = ToolRuntime(tmp_path, specs or [
        READ_FILE_SPEC, APPLY_PATCH_SPEC,
    ])
    return AgentRunner(model, tools, load_prompt_template(
        Path(__file__).resolve().parent.parent / "prompts" / "harness" / "agent-loop.md"
    ))


def _trace(tmp_path: Path) -> TraceRecorder:
    trace = TraceRecorder(tmp_path / "trace.jsonl", "run-test")
    trace.record("run_started")
    return trace


def _events(trace: TraceRecorder) -> list[dict]:
    return read_trace(trace.path)


# ---------- Runner 循环 ----------

async def test_full_loop_tool_then_answer(tmp_path):
    (tmp_path / "config.yaml").write_text("provider: deepseek\ntimeout: 10\n")
    model = FakeModel([
        json.dumps({"action": "tool", "tool": "read_file", "args": {"path": "config.yaml"}}),
        json.dumps({"action": "answer", "reply": '{"provider": "deepseek", "timeout": 10}'}),
    ])
    trace = _trace(tmp_path)
    result = await _runner(tmp_path, model, trace).run(
        "read config", ["read_file"], LIMITS, trace
    )

    assert result.finish_reason == "completed"
    assert "deepseek" in result.answer
    # observation 进入了下一次 prompt
    assert len(model.prompts) == 2
    assert "provider: deepseek" in model.prompts[1]
    # trace 生命周期配对
    kinds = [event["event"] for event in _events(trace)]
    assert kinds == [
        "run_started",
        "step_started", "prompt_rendered", "model_call_started", "model_call_finished",
        "action_parsed", "tool_call_started", "tool_call_finished", "step_finished",
        "step_started", "prompt_rendered", "model_call_started", "model_call_finished",
        "action_parsed", "step_finished",
    ]
    events = _events(trace)
    assert events[1]["data"]["step_id"] == "step-1"
    assert events[6]["data"]["tool_call_id"] == "call-1"
    assert events[6]["data"]["tool"] == "read_file"
    assert events[7]["data"]["tool_call_id"] == "call-1"


async def test_tool_step_event_keeps_full_observation_for_trace_ui(tmp_path):
    """产品 Trace 面板需要工具真实输出，Runner 事件不能再截成 500 字摘要。"""
    content = "x" * 800
    (tmp_path / "long.txt").write_text(content)
    model = FakeModel([
        json.dumps({"action": "tool", "tool": "read_file", "args": {"path": "long.txt"}}),
        json.dumps({"action": "answer", "reply": "done"}),
    ])
    trace = _trace(tmp_path)
    streamed_events = []

    await _runner(tmp_path, model, trace).run(
        "read long file", ["read_file"], LIMITS, trace,
        on_event=streamed_events.append,
    )

    tool_step = next(event for event in streamed_events if event["kind"] == "tool_step")
    assert content in tool_step["observation"]
    assert len(tool_step["observation"]) > 500


async def test_summary_event_emitted_and_not_in_answer(tmp_path):
    """action JSON 的 summary 字段 → summary 事件；不污染答案，缺省时不发事件"""
    (tmp_path / "config.yaml").write_text("provider: deepseek\n")
    model = FakeModel([
        json.dumps({"summary": "先读配置文件", "action": "tool",
                    "tool": "read_file", "args": {"path": "config.yaml"}}),
        json.dumps({"action": "answer", "reply": "done"}),  # 无 summary
    ])
    trace = _trace(tmp_path)
    streamed_events = []
    result = await _runner(tmp_path, model, trace).run(
        "read config", ["read_file"], LIMITS, trace,
        on_event=streamed_events.append,
    )

    summaries = [e for e in streamed_events if e["kind"] == "summary"]
    assert len(summaries) == 1
    assert summaries[0]["text"] == "先读配置文件"
    assert summaries[0]["step"] == 1
    # summary 早于该步工具执行
    tool_steps = [e for e in streamed_events if e["kind"] == "tool_step"]
    assert streamed_events.index(summaries[0]) < streamed_events.index(tool_steps[0])
    # 答案不含 summary
    assert result.answer == "done"


async def test_history_replays_model_raw_output(tmp_path):
    """全量回放：第二轮 prompt 同时包含第一轮模型的原始输出和工具 observation"""
    (tmp_path / "config.yaml").write_text("provider: deepseek\ntimeout: 10\n")
    first_output = json.dumps({"action": "tool", "tool": "read_file", "args": {"path": "config.yaml"}})
    model = FakeModel([
        first_output,
        json.dumps({"action": "answer", "reply": "done"}),
    ])
    trace = _trace(tmp_path)
    await _runner(tmp_path, model, trace).run("read config", ["read_file"], LIMITS, trace)

    second_prompt = model.prompts[1]
    assert f"【你】{first_output}" in second_prompt
    assert "【工具】[read_file] status=ok" in second_prompt
    assert "provider: deepseek" in second_prompt


async def test_trace_records_prompt_and_model_output_artifacts(tmp_path):
    (tmp_path / "config.yaml").write_text("provider: deepseek\n")
    model = FakeModel([
        json.dumps({"action": "tool", "tool": "read_file", "args": {"path": "config.yaml"}}),
        json.dumps({"action": "answer", "reply": "done"}),
    ])
    trace = _trace(tmp_path)
    await _runner(tmp_path, model, trace).run("read", ["read_file"], LIMITS, trace)

    events = _events(trace)
    prompt_event = next(e for e in events if e["event"] == "prompt_rendered")
    assert prompt_event["data"]["step_id"] == "step-1"
    assert prompt_event["data"]["prompt_chars"] > 0
    prompt_path = tmp_path / prompt_event["data"]["artifact"]
    assert prompt_path.is_file()
    assert prompt_path.read_text(encoding="utf-8") == model.prompts[0]

    output_event = next(e for e in events if e["event"] == "model_call_finished")
    assert output_event["data"]["duration_ms"] >= 0
    output_path = tmp_path / output_event["data"]["artifact"]
    assert json.loads(output_path.read_text(encoding="utf-8"))["action"] == "tool"

    tool_action = next(
        e for e in events if e["event"] == "action_parsed" and e["data"]["kind"] == "tool"
    )
    assert tool_action["data"]["tool"] == "read_file"
    answer_action = next(
        e for e in events if e["event"] == "action_parsed" and e["data"]["kind"] == "answer"
    )
    assert "done" in answer_action["data"]["answer_preview"]

    finished = next(e for e in events if e["event"] == "tool_call_finished")
    assert "provider: deepseek" in finished["data"]["observation"]


async def test_invalid_json_records_action_parsed(tmp_path):
    model = FakeModel([
        "not json at all",
        json.dumps({"action": "answer", "reply": "ok"}),
    ])
    trace = _trace(tmp_path)
    result = await _runner(tmp_path, model, trace).run("t", [], LIMITS, trace)

    assert result.finish_reason == "completed"
    parsed = [e for e in _events(trace) if e["event"] == "action_parsed"]
    assert parsed[0]["data"]["kind"] == "invalid"
    assert parsed[1]["data"]["kind"] == "answer"


async def test_max_steps_exhausted(tmp_path):
    model = FakeModel([
        json.dumps({"action": "tool", "tool": "read_file", "args": {"path": f"x{i}.txt"}})
        for i in range(3)
    ])
    trace = _trace(tmp_path)
    limits = RunLimits(max_steps=3, timeout_seconds=30)
    result = await _runner(tmp_path, model, trace).run(
        "never answer", ["read_file"], limits, trace
    )
    assert result.finish_reason == "max_steps"
    steps = [e for e in _events(trace) if e["event"] == "step_started"]
    assert len(steps) == 3


async def test_bare_json_answer_accepted(tmp_path):
    """模型直接输出无 action 外壳的答案 JSON 时按 answer 接受"""
    model = FakeModel(['{"y2022": 2606, "y2023": 2891}'])
    trace = _trace(tmp_path)
    result = await _runner(tmp_path, model, trace).run("t", [], LIMITS, trace)

    assert result.finish_reason == "completed"
    assert result.answer == {"y2022": 2606, "y2023": 2891}
    parsed = [e for e in _events(trace) if e["event"] == "action_parsed"]
    assert parsed[0]["data"]["kind"] == "answer"


async def test_repeated_failure_aborts_before_third_call(tmp_path):
    model = FakeModel([
        json.dumps({"action": "tool", "tool": "read_file", "args": {"path": "../escape"}}),
        json.dumps({"action": "tool", "tool": "read_file", "args": {"path": "../escape"}}),
    ])
    trace = _trace(tmp_path)
    result = await _runner(tmp_path, model, trace).run(
        "loop", ["read_file"], LIMITS, trace
    )
    assert result.finish_reason == "error"
    assert "repeated" in result.error
    errors = [e for e in _events(trace) if e["event"] == "tool_call_error"]
    assert len(errors) == 1  # 第二次重复在执行前终止，trace 不留重复失败


def _echo_spec(name: str, observation: str) -> ToolSpec:
    """成功但每次返回固定 observation 的 stub：模拟"换查询却拿回相同信息"。"""
    def handler(workspace: Path, args: dict) -> ToolResult:
        return ToolResult(status="ok", observation=observation)
    return ToolSpec(name=name, description="echo", args_description="{}", handler=handler)


async def test_no_progress_stall_forces_answer(tmp_path):
    """成功工具连续返回相同 observation（args 每次微调）→ 判无进展并强制收尾。

    baseline（改动前）行为：三次相同结果全部执行、observation 预算累加、
    最终因步数耗尽落到 max_steps。改动后应在第二次相同结果时强制收尾作答。
    """
    spec = _echo_spec("recall", "status=ok\n没有找到相关内容")
    model = FakeModel([
        json.dumps({"action": "tool", "tool": "recall", "args": {"q": "博通"}}),
        json.dumps({"action": "tool", "tool": "recall", "args": {"q": "博通 Broadcom"}}),
        json.dumps({"action": "tool", "tool": "recall", "args": {"q": "Broadcom 博通"}}),
        json.dumps({"action": "answer", "reply": "基于已有信息作答"}),
    ])
    tools = ToolRuntime(tmp_path, [spec])
    runner = AgentRunner(model, tools, load_prompt_template(
        Path(__file__).resolve().parent.parent / "prompts" / "harness" / "agent-loop.md"
    ))
    trace = _trace(tmp_path)
    result = await runner.run("对比博通", ["recall"], LIMITS, trace)

    # 强制收尾：拿到答案而非报错/耗尽
    assert result.finish_reason == "completed"
    assert result.answer is not None
    # 内容去重是执行后判定：首次结果记录、两次重复各触发一次无进展
    events = _events(trace)
    stalls = [e for e in events if e["event"] == "no_progress_detected"]
    assert len(stalls) == 2
    assert stalls[0]["data"]["forced_answer"] is False  # 首次重复只 warning
    assert stalls[1]["data"]["forced_answer"] is True   # 二次重复强制收尾
    assert stalls[1]["data"]["repeated_from_step"] == 1  # 都追溯到首次出现的 step


async def test_invalid_json_feedback_then_recover(tmp_path):
    model = FakeModel([
        "这不是 JSON",
        json.dumps({"action": "answer", "reply": "ok"}),
    ])
    trace = _trace(tmp_path)
    result = await _runner(tmp_path, model, trace).run("task", [], LIMITS, trace)
    assert result.finish_reason == "completed"
    assert result.answer == "ok"
    assert "格式不对" in model.prompts[1]


# ---------- 工具 ----------

def _execute(tmp_path: Path, spec: ToolSpec, name: str, args: dict, allowed=None):
    tools = ToolRuntime(tmp_path, [spec])
    return asyncio.run(tools.execute(name, args, allowed if allowed is not None else [name]))


def test_read_file_path_traversal_denied(tmp_path):
    for path in ("../secret", "/etc/passwd", "sub/../../secret"):
        result = _execute(tmp_path, READ_FILE_SPEC, "read_file", {"path": path})
        assert result.status == "denied", path


def test_read_file_symlink_escape_denied(tmp_path):
    outside = tmp_path.parent / "outside-secret.txt"
    outside.write_text("secret", encoding="utf-8")
    (tmp_path / "link.txt").symlink_to(outside)
    result = _execute(tmp_path, READ_FILE_SPEC, "read_file", {"path": "link.txt"})
    assert result.status == "denied"


def test_search_skips_symlink_to_file_outside_workspace(tmp_path):
    outside = tmp_path.parent / f"{tmp_path.name}-search-secret.txt"
    outside.write_text("OUTSIDE-SEARCH-SECRET", encoding="utf-8")
    (tmp_path / "link.txt").symlink_to(outside)

    result = _execute(tmp_path, SEARCH_SPEC, "search", {"query": "OUTSIDE-SEARCH-SECRET"})

    assert result.status == "ok"
    assert "OUTSIDE-SEARCH-SECRET" not in result.observation
    assert "找到 0 处匹配" in result.observation


def test_read_file_truncates(tmp_path):
    (tmp_path / "big.txt").write_text("x" * 20000, encoding="utf-8")
    result = _execute(tmp_path, READ_FILE_SPEC, "read_file", {"path": "big.txt"})
    assert result.status == "ok"
    assert result.truncated
    assert result.observation.startswith("[chars 0-16000 of 20000, truncated]\n")
    assert len(result.observation.split("\n", 1)[1]) == 16000


def test_read_file_offset_paginates(tmp_path):
    """offset 让 LLM 分段读取：第一次读 0-4000，第二次读 4000-8000"""
    (tmp_path / "big.txt").write_text("x" * 8000, encoding="utf-8")
    r1 = _execute(tmp_path, READ_FILE_SPEC, "read_file",
                  {"path": "big.txt", "max_chars": 4000})
    assert r1.status == "ok"
    assert r1.truncated
    assert r1.observation.startswith("[chars 0-4000 of 8000, truncated]\n")
    # observation 里的范围元信息直接给出下一页 offset
    r2 = _execute(tmp_path, READ_FILE_SPEC, "read_file", {"path": "big.txt", "offset": 4000})
    assert r2.status == "ok"
    assert not r2.truncated
    assert r2.observation.startswith("[chars 4000-8000 of 8000]\n")
    # 两页内容拼回原文件
    assert r1.observation.split("\n", 1)[1] + r2.observation.split("\n", 1)[1] == "x" * 8000


def test_read_file_offset_at_end(tmp_path):
    """offset 超出文件长度时明确提示，避免与空文件混淆"""
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
    result = _execute(tmp_path, READ_FILE_SPEC, "read_file", {"path": "a.txt", "offset": 10})
    assert result.status == "ok"
    assert result.observation == "offset 10 beyond end of file (total 5 chars)"
    assert not result.truncated


def test_read_file_not_found(tmp_path):
    result = _execute(tmp_path, READ_FILE_SPEC, "read_file", {"path": "missing.txt"})
    assert result.status == "error"


def test_write_file_creates_new_file(tmp_path):
    result = _execute(tmp_path, WRITE_FILE_SPEC, "write_file", {
        "path": "wiki/notes/new.md", "content": "# 新页面\n",
    })
    assert result.status == "ok"
    assert (tmp_path / "wiki" / "notes" / "new.md").read_text() == "# 新页面\n"


def test_write_file_refuses_overwrite_by_default(tmp_path):
    (tmp_path / "a.md").write_text("original", encoding="utf-8")
    result = _execute(tmp_path, WRITE_FILE_SPEC, "write_file", {
        "path": "a.md", "content": "changed",
    })
    assert result.status == "denied"
    assert result.error_code == "already_exists"
    assert (tmp_path / "a.md").read_text() == "original"

    allowed = _execute(tmp_path, WRITE_FILE_SPEC, "write_file", {
        "path": "a.md", "content": "changed", "overwrite": True,
    })
    assert allowed.status == "ok"
    assert (tmp_path / "a.md").read_text() == "changed"


def test_write_file_path_traversal_denied(tmp_path):
    result = _execute(tmp_path, WRITE_FILE_SPEC, "write_file", {
        "path": "../escape.md", "content": "x",
    })
    assert result.status == "denied"
    assert not (tmp_path.parent / "escape.md").exists()


def test_apply_patch_replaces_unique(tmp_path):
    (tmp_path / "config.yaml").write_text("timeout: 5\nretries: 3\n")
    result = _execute(tmp_path, APPLY_PATCH_SPEC, "apply_patch", {
        "path": "config.yaml", "old": "timeout: 5", "new": "timeout: 10",
    })
    assert result.status == "ok"
    assert (tmp_path / "config.yaml").read_text() == "timeout: 10\nretries: 3\n"


def test_apply_patch_rejects_non_unique_or_missing_old(tmp_path):
    (tmp_path / "a.txt").write_text("dup\ndup\n")
    result = _execute(tmp_path, APPLY_PATCH_SPEC, "apply_patch", {
        "path": "a.txt", "old": "dup", "new": "x",
    })
    assert result.status == "invalid_input"
    result = _execute(tmp_path, APPLY_PATCH_SPEC, "apply_patch", {
        "path": "a.txt", "old": "nope", "new": "x",
    })
    assert result.status == "invalid_input"


def test_apply_patch_path_escape_denied(tmp_path):
    result = _execute(tmp_path, APPLY_PATCH_SPEC, "apply_patch", {
        "path": "../outside.txt", "old": "a", "new": "b",
    })
    assert result.status == "denied"


def test_tool_not_in_allowed_denied(tmp_path):
    result = _execute(tmp_path, READ_FILE_SPEC, "read_file",
                      {"path": "a.txt"}, allowed=[])
    assert result.status == "denied"


# ---------- search 工具 ----------

def test_search_literal_hit_offset(tmp_path):
    content = "line one\ntarget here\nline three\n"
    (tmp_path / "a.txt").write_text(content, encoding="utf-8")
    result = _execute(tmp_path, SEARCH_SPEC, "search", {"query": "target"})
    assert result.status == "ok"
    assert result.observation.startswith("找到 1 处匹配:")
    expected_offset = content.index("target here")
    assert f"a.txt [chars {expected_offset}]" in result.observation
    # 命中行带前后各一行上下文
    assert "line one" in result.observation and "line three" in result.observation


def test_search_multiple_results_sorted_by_offset(tmp_path):
    (tmp_path / "a.txt").write_text("x\ntarget\ny\ntarget\n", encoding="utf-8")
    result = _execute(tmp_path, SEARCH_SPEC, "search", {"query": "target"})
    assert result.status == "ok"
    assert result.observation.startswith("找到 2 处匹配:")
    offsets = [int(line.split("[chars ")[1].split("]")[0])
               for line in result.observation.splitlines() if "[chars " in line]
    assert offsets == sorted(offsets)


def test_search_max_results_truncates(tmp_path):
    (tmp_path / "a.txt").write_text("hit\n" * 5, encoding="utf-8")
    result = _execute(tmp_path, SEARCH_SPEC, "search",
                      {"query": "hit", "max_results": 2})
    assert result.status == "ok"
    hits = [line for line in result.observation.splitlines() if "[chars " in line]
    assert len(hits) == 2
    assert "仅显示前 2 处" in result.observation


def test_search_path_traversal_denied(tmp_path):
    result = _execute(tmp_path, SEARCH_SPEC, "search",
                      {"query": "x", "path": "../escape"})
    assert result.status == "denied"


def test_search_invalid_regex_falls_back_to_literal(tmp_path):
    (tmp_path / "a.txt").write_text("value: re:(\nplain\n", encoding="utf-8")
    result = _execute(tmp_path, SEARCH_SPEC, "search", {"query": "re:("})
    assert result.status == "ok"  # 非法正则不报错，回退为字面搜索
    assert "找到 1 处匹配:" in result.observation


def test_search_regex_prefix_matches_pattern(tmp_path):
    (tmp_path / "a.txt").write_text("abc123\nxyz\n", encoding="utf-8")
    result = _execute(tmp_path, SEARCH_SPEC, "search",
                      {"query": r"re:[a-z]+\d+"})
    assert result.status == "ok"
    assert "abc123" in result.observation


# ---------- list_files 工具 ----------

def test_list_files_tree_with_sizes(tmp_path):
    (tmp_path / "config.yaml").write_text("a" * 128, encoding="utf-8")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "x.txt").write_text("hello", encoding="utf-8")
    (sub / "y.txt").write_text("world", encoding="utf-8")
    result = _execute(tmp_path, LIST_FILES_SPEC, "list_files", {})
    assert result.status == "ok"
    assert "📄 config.yaml (128B)" in result.observation
    assert "📁 sub/ (2 项)" in result.observation
    assert "📄 x.txt (5B)" in result.observation


def test_list_files_does_not_traverse_symlink_directory_outside_workspace(tmp_path):
    outside = tmp_path.parent / f"{tmp_path.name}-outside-dir"
    outside.mkdir()
    (outside / "hidden.txt").write_text("secret", encoding="utf-8")
    (tmp_path / "linked-dir").symlink_to(outside, target_is_directory=True)

    result = _execute(tmp_path, LIST_FILES_SPEC, "list_files", {"max_depth": 2})

    assert result.status == "ok"
    assert "hidden.txt" not in result.observation
    assert "linked-dir" in result.observation
    assert "已跳过 symlink" in result.observation


def test_list_files_max_depth_limits_expansion(tmp_path):
    deep = tmp_path / "a" / "b"
    deep.mkdir(parents=True)
    (deep / "leaf.txt").write_text("x", encoding="utf-8")
    result = _execute(tmp_path, LIST_FILES_SPEC, "list_files",
                      {"max_depth": 1})
    assert result.status == "ok"
    assert "📁 a/" in result.observation
    assert "leaf.txt" not in result.observation
    assert "📁 b/" not in result.observation


def test_list_files_path_traversal_denied(tmp_path):
    result = _execute(tmp_path, LIST_FILES_SPEC, "list_files",
                      {"path": "../escape"})
    assert result.status == "denied"


# ---------- apply_patch 失败反馈增强 ----------

def test_apply_patch_non_unique_lists_offsets(tmp_path):
    (tmp_path / "a.txt").write_text("head\ntimeout: 5\nmid\ntimeout: 5\n", encoding="utf-8")
    result = _execute(tmp_path, APPLY_PATCH_SPEC, "apply_patch", {
        "path": "a.txt", "old": "timeout: 5", "new": "timeout: 10",
    })
    assert result.status == "invalid_input"
    assert "old occurs 2 times, must occur exactly once. 出现位置:" in result.observation
    assert "[chars 5] ...timeout: 5..." in result.observation
    assert "[chars 20] ...timeout: 5..." in result.observation


def test_apply_patch_zero_occurrences_message_unchanged(tmp_path):
    (tmp_path / "a.txt").write_text("hello\n", encoding="utf-8")
    result = _execute(tmp_path, APPLY_PATCH_SPEC, "apply_patch", {
        "path": "a.txt", "old": "nope", "new": "x",
    })
    assert result.status == "invalid_input"
    assert result.observation == "old occurs 0 times, must occur exactly once"


# ---------- observation 累计量埋点 ----------

async def test_observation_chars_accumulate_in_trace(tmp_path):
    (tmp_path / "a.txt").write_text("aaa", encoding="utf-8")
    (tmp_path / "b.txt").write_text("bbbbb", encoding="utf-8")
    model = FakeModel([
        json.dumps({"action": "tool", "tool": "read_file", "args": {"path": "a.txt"}}),
        json.dumps({"action": "tool", "tool": "read_file", "args": {"path": "b.txt"}}),
        json.dumps({"action": "answer", "reply": "done"}),
    ])
    trace = _trace(tmp_path)
    result = await _runner(tmp_path, model, trace).run(
        "task", ["read_file"], LIMITS, trace
    )
    assert result.finish_reason == "completed"
    finished = [e for e in _events(trace) if e["event"] == "tool_call_finished"]
    assert len(finished) == 2
    first, second = finished[0]["data"], finished[1]["data"]
    assert first["observation_chars"] > 0
    assert first["total_observation_chars"] == first["observation_chars"]
    assert second["total_observation_chars"] == (
        first["observation_chars"] + second["observation_chars"]
    )


# ---------- 异步工具 / usage / 预算 ----------

async def test_async_tool_handler_is_awaited(tmp_path):
    """async handler 在一个 run 内被正确 await，同步 handler 也不受影响"""
    calls = []

    async def async_handler(workspace: Path, args: dict) -> ToolResult:
        await asyncio.sleep(0)  # 让出事件循环，证明确实被 await
        calls.append(args)
        (workspace / "async.txt").write_text("written by async tool", encoding="utf-8")
        return ToolResult(status="ok", observation="async-done")

    spec = ToolSpec(name="async_tool", description="d", args_description="a",
                    handler=async_handler)
    model = FakeModel([
        json.dumps({"action": "tool", "tool": "async_tool", "args": {"x": 1}}),
        json.dumps({"action": "tool", "tool": "read_file", "args": {"path": "async.txt"}}),
        json.dumps({"action": "answer", "reply": "done"}),
    ])
    trace = _trace(tmp_path)
    tools = ToolRuntime(tmp_path, [spec, READ_FILE_SPEC])
    runner = AgentRunner(model, tools, load_prompt_template(
        Path(__file__).resolve().parent.parent / "prompts" / "harness" / "agent-loop.md"
    ))
    result = await runner.run("task", ["async_tool", "read_file"], LIMITS, trace)

    assert result.finish_reason == "completed"
    assert calls == [{"x": 1}]
    # 异步工具的 observation 进入后续 prompt，且同步工具读到了它写的文件
    assert "async-done" in model.prompts[1]
    assert "written by async tool" in model.prompts[2]


async def test_usage_accumulates_into_result(tmp_path):
    """每次模型调用的 usage 累计进 AgentResult，成本按 token_tracker 估算"""
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    u1 = TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150, model="m")
    u2 = TokenUsage(prompt_tokens=200, completion_tokens=80, total_tokens=280, model="m")
    model = FakeModel([
        (json.dumps({"action": "tool", "tool": "read_file", "args": {"path": "a.txt"}}), u1),
        (json.dumps({"action": "answer", "reply": "done"}), u2),
    ])
    trace = _trace(tmp_path)
    result = await _runner(tmp_path, model, trace).run("t", ["read_file"], LIMITS, trace)

    assert result.finish_reason == "completed"
    assert result.usage is not None
    assert result.usage.prompt_tokens == 300
    assert result.usage.completion_tokens == 130
    assert result.usage.total_tokens == 430
    assert result.cost_usd == result.usage.total_cost > 0
    finished = [e for e in _events(trace) if e["event"] == "model_call_finished"]
    assert finished[0]["data"]["prompt_tokens"] == 100
    assert finished[1]["data"]["total_tokens"] == 280


async def test_result_usage_defaults_when_model_reports_none(tmp_path):
    """模型不返回 usage 时只记录 0 成本，不影响既有行为"""
    model = FakeModel([json.dumps({"action": "answer", "reply": "done"})])
    trace = _trace(tmp_path)
    result = await _runner(tmp_path, model, trace).run("t", [], LIMITS, trace)

    assert result.finish_reason == "completed"
    assert result.usage is None
    assert result.cost_usd == 0.0


async def test_budget_exceeded_terminates_before_tool_call(tmp_path):
    """累计成本超限后以 budget_exceeded 终止，且不再执行后续工具"""
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    # 1M prompt tokens × $2/M = $2.0 成本
    costly = TokenUsage(prompt_tokens=1_000_000, total_tokens=1_000_000, model="m")
    model = FakeModel([
        (json.dumps({"action": "tool", "tool": "read_file", "args": {"path": "a.txt"}}), costly),
    ])
    trace = _trace(tmp_path)
    limits = RunLimits(max_steps=5, timeout_seconds=30, max_cost_usd=1.0)
    result = await _runner(tmp_path, model, trace).run("t", ["read_file"], limits, trace)

    assert result.finish_reason == "budget_exceeded"
    assert result.usage is not None
    assert result.cost_usd > 1.0
    events = _events(trace)
    assert not any(e["event"] == "tool_call_started" for e in events)
    budget = next(e for e in events if e["event"] == "budget_exceeded")
    assert budget["data"]["max_cost_usd"] == 1.0


async def test_budget_does_not_discard_final_answer(tmp_path):
    """超限的那次调用恰好产出最终答案时，答案仍按 completed 返回"""
    costly = TokenUsage(prompt_tokens=1_000_000, total_tokens=1_000_000, model="m")
    model = FakeModel([
        (json.dumps({"action": "answer", "reply": "done"}), costly),
    ])
    trace = _trace(tmp_path)
    limits = RunLimits(max_steps=5, timeout_seconds=30, max_cost_usd=1.0)
    result = await _runner(tmp_path, model, trace).run("t", [], limits, trace)

    assert result.finish_reason == "completed"
    assert result.answer == "done"
    assert result.cost_usd > 1.0


async def test_zero_budget_means_unlimited(tmp_path):
    """max_cost_usd=0（evals 任务的"未设置"约定）不触发预算终止"""
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    costly = TokenUsage(prompt_tokens=1_000_000, total_tokens=1_000_000, model="m")
    model = FakeModel([
        (json.dumps({"action": "tool", "tool": "read_file", "args": {"path": "a.txt"}}), costly),
        json.dumps({"action": "answer", "reply": "done"}),
    ])
    trace = _trace(tmp_path)
    result = await _runner(tmp_path, model, trace).run("t", ["read_file"], LIMITS, trace)

    assert result.finish_reason == "completed"


# ---------- 超时 ----------

async def test_timeout_cancels_model_call_at_deadline(tmp_path):
    """总 deadline 必须中断当前模型调用，而不是等当前 step 自己返回。"""
    cancelled = asyncio.Event()

    class SlowModel:
        def __init__(self):
            self.prompts: list[str] = []

        async def complete(self, prompt: str):
            self.prompts.append(prompt)
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                cancelled.set()
                raise

    model = SlowModel()
    trace = _trace(tmp_path)
    limits = RunLimits(max_steps=5, timeout_seconds=0.01)
    result = await _runner(tmp_path, model, trace).run("t", ["read_file"], limits, trace)

    assert result.finish_reason == "timeout"
    assert "timeout" in result.error
    assert cancelled.is_set()
    assert len(model.prompts) == 1
    events = _events(trace)
    assert len([e for e in events if e["event"] == "step_started"]) == 1
    timeout_event = next(e for e in events if e["event"] == "timeout")
    assert timeout_event["data"]["timeout_seconds"] == 0.01


async def test_timeout_cancels_tool_call_at_deadline(tmp_path):
    """总 deadline 同样必须中断挂起的工具 handler。"""
    cancelled = asyncio.Event()

    async def hanging_tool(workspace, args):
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    spec = ToolSpec(
        name="hang", description="hang", args_description="{}", handler=hanging_tool,
    )
    model = FakeModel([
        json.dumps({"action": "tool", "tool": "hang", "args": {}}),
    ])
    trace = _trace(tmp_path)
    result = await _runner(tmp_path, model, trace, [spec]).run(
        "t", ["hang"], RunLimits(max_steps=3, timeout_seconds=0.01), trace,
    )

    assert result.finish_reason == "timeout"
    assert cancelled.is_set()
    assert any(event["event"] == "timeout" for event in _events(trace))


async def test_provider_timeout_before_run_deadline_is_not_misclassified(tmp_path):
    class ProviderTimeoutModel:
        async def complete(self, prompt: str):
            raise TimeoutError("provider request timed out")

    trace = _trace(tmp_path)
    with pytest.raises(TimeoutError, match="provider request timed out"):
        await _runner(tmp_path, ProviderTimeoutModel(), trace).run(
            "t", [], RunLimits(max_steps=3, timeout_seconds=30), trace,
        )

    assert not any(event["event"] == "timeout" for event in _events(trace))


async def test_runner_truncates_single_and_total_tool_observations(tmp_path):
    """工具输出必须受单次和全 run observation 预算约束。"""
    from harness.runner import MAX_OBSERVATION_CHARS, MAX_TOTAL_OBSERVATION_CHARS

    def large_tool(workspace, args):
        # 每次内容不同（前缀带 n），避免触发无进展检测，专注验证截断预算
        head = f"chunk-{args.get('n')}\n"
        return ToolResult(status="ok", observation=head + "x" * (MAX_OBSERVATION_CHARS * 2))

    spec = ToolSpec(
        name="large", description="large", args_description="{}", handler=large_tool,
    )
    calls_to_exhaust = MAX_TOTAL_OBSERVATION_CHARS // MAX_OBSERVATION_CHARS
    model = FakeModel([
        json.dumps({"action": "tool", "tool": "large", "args": {"n": index}})
        for index in range(calls_to_exhaust)
    ] + [json.dumps({"action": "answer", "reply": "done"})])
    trace = _trace(tmp_path)
    result = await _runner(tmp_path, model, trace, [spec]).run(
        "t", ["large"], RunLimits(max_steps=calls_to_exhaust + 2, timeout_seconds=30), trace,
    )

    assert result.finish_reason == "completed"
    finished = [event for event in _events(trace)
                if event["event"] == "tool_call_finished"]
    assert finished
    assert all(event["data"]["observation_chars"] <= MAX_OBSERVATION_CHARS
               for event in finished)
    assert finished[-1]["data"]["total_observation_chars"] <= MAX_TOTAL_OBSERVATION_CHARS
    assert "truncated" in model.prompts[1]


async def test_zero_timeout_means_unlimited(tmp_path):
    """timeout_seconds=0/None 表示不限制（与 max_cost_usd 约定一致）"""
    model = FakeModel([json.dumps({"action": "answer", "reply": "done"})])
    trace = _trace(tmp_path)
    for timeout in (0, -1, None):
        limits = RunLimits(max_steps=5, timeout_seconds=timeout)
        result = await _runner(tmp_path, model, trace).run("t", [], limits, trace)
        assert result.finish_reason == "completed", timeout


# ---------- lucas_single adapter ----------

async def test_lucas_single_adapter_parses_json_answer(tmp_path, monkeypatch):
    from evals.harness.adapters.lucas_single import LucasSingleAgent

    model = FakeModel([
        json.dumps({"action": "answer", "reply": '结果：{"provider": "deepseek", "timeout": 10}'})
    ])
    adapter = LucasSingleAgent(model_adapter=model)
    trace = _trace(tmp_path)
    result = await adapter.run("task", tmp_path, ["read_file"], LIMITS, trace)
    assert result.answer == {"provider": "deepseek", "timeout": 10}


async def test_lucas_single_adapter_keeps_plain_string_answer(tmp_path):
    from evals.harness.adapters.lucas_single import LucasSingleAgent

    model = FakeModel([json.dumps({"action": "answer", "reply": "plain text"})])
    adapter = LucasSingleAgent(model_adapter=model)
    trace = _trace(tmp_path)
    result = await adapter.run("task", tmp_path, ["read_file"], LIMITS, trace)
    assert result.answer == "plain text"


def test_suite_registers_lucas_single(monkeypatch):
    import evals.harness.suite as suite

    class _StubAdapter:
        variant = "lucas-single"

    monkeypatch.setattr(suite, "LucasSingleAgent", lambda: _StubAdapter())
    task = load_task_fixture()
    adapter = suite.build_adapter("lucas-single", task)
    assert adapter.variant == "lucas-single"


def load_task_fixture():
    from evals.harness.models import TaskSpec
    return TaskSpec(
        id="T", title="t", instruction="i", fixture="fixture",
        allowed_tools=[], limits=LIMITS,
        outcome_graders=[], safety_graders=[], process_graders=[],
        tags=[], task_dir=Path("."),
    )
