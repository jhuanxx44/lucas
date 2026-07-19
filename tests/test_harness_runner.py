import json
from pathlib import Path

import pytest

from evals.harness.models import RunLimits
from evals.harness.trace import TraceRecorder, read_trace
from harness.runner import AgentRunner, load_prompt_template
from harness.tools.base import ToolSpec
from harness.tools.filesystem import APPLY_PATCH_SPEC, READ_FILE_SPEC
from harness.tools.process import make_run_tests_spec
from harness.tools.registry import ToolRuntime

LIMITS = RunLimits(max_steps=5, timeout_seconds=30)


class FakeModel:
    """按脚本依次返回固定响应"""

    def __init__(self, responses: list[str]):
        self.responses = list(responses)
        self.prompts: list[str] = []

    async def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if self.responses:
            return self.responses.pop(0)
        return json.dumps({"action": "answer", "reply": "fallback"})


def _runner(tmp_path: Path, model: FakeModel, trace: TraceRecorder, specs=None):
    tools = ToolRuntime(tmp_path, specs or [
        READ_FILE_SPEC, APPLY_PATCH_SPEC, make_run_tests_spec(),
    ])
    return AgentRunner(model, tools, load_prompt_template(
        Path(__file__).resolve().parent.parent / "prompts" / "harness" / "tool-loop.md"
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
        "step_started", "tool_call_started", "tool_call_finished", "step_finished",
        "step_started", "step_finished",
    ]
    events = _events(trace)
    assert events[1]["data"]["step_id"] == "step-1"
    assert events[2]["data"]["tool_call_id"] == "call-1"
    assert events[2]["data"]["tool"] == "read_file"
    assert events[3]["data"]["tool_call_id"] == "call-1"


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


async def test_invalid_json_feedback_then_recover(tmp_path):
    model = FakeModel([
        "这不是 JSON",
        json.dumps({"action": "answer", "reply": "ok"}),
    ])
    trace = _trace(tmp_path)
    result = await _runner(tmp_path, model, trace).run("task", [], LIMITS, trace)
    assert result.finish_reason == "completed"
    assert result.answer == "ok"
    assert "不是合法 JSON" in model.prompts[1]


# ---------- 工具 ----------

def _execute(tmp_path: Path, spec: ToolSpec, name: str, args: dict, allowed=None):
    tools = ToolRuntime(tmp_path, [spec])
    return tools.execute(name, args, allowed if allowed is not None else [name])


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


def test_read_file_truncates(tmp_path):
    (tmp_path / "big.txt").write_text("x" * 5000, encoding="utf-8")
    result = _execute(tmp_path, READ_FILE_SPEC, "read_file", {"path": "big.txt"})
    assert result.status == "ok"
    assert result.truncated
    assert len(result.observation) == 4000


def test_read_file_not_found(tmp_path):
    result = _execute(tmp_path, READ_FILE_SPEC, "read_file", {"path": "missing.txt"})
    assert result.status == "error"


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


def test_run_tests_rejects_non_pytest(tmp_path):
    result = _execute(tmp_path, make_run_tests_spec(), "run_tests",
                      {"command": ["rm", "-rf", "."]})
    assert result.status == "denied"


def test_run_tests_passes(tmp_path):
    (tmp_path / "test_ok.py").write_text("def test_ok():\n    assert True\n")
    result = _execute(tmp_path, make_run_tests_spec(), "run_tests",
                      {"command": ["pytest", "test_ok.py", "-q"]})
    assert result.status == "ok"
    assert "exit code: 0" in result.observation


def test_run_tests_timeout_kills(tmp_path):
    (tmp_path / "test_slow.py").write_text(
        "import time\n\ndef test_slow():\n    time.sleep(30)\n"
    )
    result = _execute(tmp_path, make_run_tests_spec(default_timeout=1), "run_tests",
                      {"command": ["pytest", "test_slow.py", "-q"]})
    assert result.status == "timeout"


def test_tool_not_in_allowed_denied(tmp_path):
    result = _execute(tmp_path, READ_FILE_SPEC, "read_file",
                      {"path": "a.txt"}, allowed=[])
    assert result.status == "denied"


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
