import asyncio
import json
from dataclasses import replace
from pathlib import Path

import pytest

from evals.harness.grader import check_trace_integrity, grade_trial
from evals.harness.models import AgentResult, RunLimits, TaskSpec, load_suite, load_task
from evals.harness.runner import run_trial
from evals.harness.suite import run_suite
from evals.harness.trace import TraceRecorder
from evals.harness.validation import validate_task
from evals.harness.workspace import TrialWorkspace


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _task(tmp_path: Path, *, process=None, safety=None) -> TaskSpec:
    fixture = tmp_path / "fixture"
    reference = tmp_path / "reference"
    fixture.mkdir(exist_ok=True)
    reference.mkdir(exist_ok=True)
    return TaskSpec(
        id="TEST-01",
        title="test",
        instruction="test",
        fixture="fixture",
        allowed_tools=["read_file"],
        limits=RunLimits(max_steps=5, timeout_seconds=5),
        outcome_graders=[],
        safety_graders=safety or [],
        process_graders=process or [],
        tags=[],
        task_dir=tmp_path,
    )


def _valid_trace(path: Path, run_id: str, events=None, finish_reason="completed"):
    trace = TraceRecorder(path, run_id)
    trace.record("run_started")
    for event, data in events or []:
        trace.record(event, data)
    trace.record("run_finished", {"finish_reason": finish_reason})
    return trace


def test_trial_workspaces_are_fresh_and_isolated(tmp_path):
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    (fixture / "value.txt").write_text("original", encoding="utf-8")
    cache = fixture / "__pycache__"
    cache.mkdir()
    (cache / "fixture.pyc").write_bytes(b"not task data")

    first = TrialWorkspace(fixture)
    second = TrialWorkspace(fixture)
    try:
        (first.root / "value.txt").write_text("changed", encoding="utf-8")

        assert first.root != second.root
        assert (second.root / "value.txt").read_text(encoding="utf-8") == "original"
        assert not (second.root / "__pycache__").exists()
        assert first.changes() == {"value.txt": "modified"}
        assert second.changes() == {}
    finally:
        first.cleanup()
        second.cleanup()


def test_trace_integrity_accepts_balanced_lifecycle(tmp_path):
    path = tmp_path / "trace.jsonl"
    _valid_trace(path, "run-1", [
        ("step_started", {"step_id": "step-1"}),
        ("tool_call_started", {
            "tool_call_id": "call-1", "tool": "read_file", "args": {"path": "a.txt"}
        }),
        ("tool_call_finished", {"tool_call_id": "call-1"}),
        ("step_finished", {"step_id": "step-1"}),
    ])

    assert check_trace_integrity(path, "run-1")["passed"] is True


def test_trace_integrity_rejects_unfinished_call(tmp_path):
    path = tmp_path / "trace.jsonl"
    _valid_trace(path, "run-1", [
        ("tool_call_started", {
            "tool_call_id": "call-1", "tool": "read_file", "args": {}
        }),
    ])

    result = check_trace_integrity(path, "run-1")

    assert result["passed"] is False
    assert "unfinished tool_call" in result["detail"]


def test_all_process_graders_accept_valid_trace(tmp_path):
    task = _task(tmp_path, process=[
        {"type": "allowed_tools", "tools": ["read_file"], "required": True},
        {"type": "max_tool_calls", "value": 1, "required": True},
        {"type": "max_steps", "value": 1, "required": True},
        {"type": "no_repeated_failure", "max_consecutive": 1, "required": True},
        {"type": "finish_reason", "allowed": ["completed"], "required": True},
    ])
    trace = _valid_trace(tmp_path / "trace.jsonl", "run-1", [
        ("step_started", {"step_id": "step-1"}),
        ("tool_call_started", {
            "tool_call_id": "call-1", "tool": "read_file", "args": {"path": "a.txt"}
        }),
        ("tool_call_finished", {"tool_call_id": "call-1"}),
        ("step_finished", {"step_id": "step-1"}),
    ])

    grade = grade_trial(task, task.fixture_dir, {}, AgentResult(), trace.path, "run-1")

    assert grade.process_passed is True
    assert grade.success is True


def test_answer_facts_accepts_equivalent_wording_and_normalized_paths(tmp_path):
    task = replace(_task(tmp_path), outcome_graders=[{
        "type": "answer_facts",
        "query_id": "Q1",
        "fact_groups": [["DDR4"], ["低功耗記憶體", "LPDDR"]],
        "evidence_paths": ["companies/南亞科技.md"],
        "required": True,
    }])
    trace = _valid_trace(tmp_path / "trace.jsonl", "run-1")
    result = AgentResult(answer={
        "query_id": "Q1",
        "facts": ["DDR4", "低功耗動態隨機存取記憶體（LPDDR）"],
        "evidence_paths": ["wiki/companies/南亞科技.md"],
    })

    grade = grade_trial(task, task.fixture_dir, {}, result, trace.path, "run-1")

    assert grade.outcome_passed is True


@pytest.mark.parametrize(
    ("grader", "events", "finish_reason", "check_name"),
    [
        (
            {"type": "allowed_tools", "tools": ["read_file"], "required": True},
            [
                ("tool_call_started", {"tool_call_id": "c1", "tool": "shell", "args": {}}),
                ("tool_call_finished", {"tool_call_id": "c1"}),
            ],
            "completed",
            "allowed_tools",
        ),
        (
            {"type": "max_tool_calls", "value": 1, "required": True},
            [
                ("tool_call_started", {"tool_call_id": "c1", "tool": "read_file", "args": {}}),
                ("tool_call_finished", {"tool_call_id": "c1"}),
                ("tool_call_started", {"tool_call_id": "c2", "tool": "read_file", "args": {}}),
                ("tool_call_finished", {"tool_call_id": "c2"}),
            ],
            "completed",
            "max_tool_calls",
        ),
        (
            {"type": "max_steps", "value": 1, "required": True},
            [
                ("step_started", {"step_id": "s1"}),
                ("step_finished", {"step_id": "s1"}),
                ("step_started", {"step_id": "s2"}),
                ("step_finished", {"step_id": "s2"}),
            ],
            "completed",
            "max_steps",
        ),
        (
            {"type": "no_repeated_failure", "max_consecutive": 1, "required": True},
            [
                ("tool_call_started", {
                    "tool_call_id": "c1", "tool": "read_file", "args": {"path": "missing"}
                }),
                ("tool_call_error", {"tool_call_id": "c1"}),
                ("tool_call_started", {
                    "tool_call_id": "c2", "tool": "read_file", "args": {"path": "missing"}
                }),
                ("tool_call_error", {"tool_call_id": "c2"}),
            ],
            "completed",
            "no_repeated_failure",
        ),
        (
            {"type": "finish_reason", "allowed": ["completed"], "required": True},
            [],
            "unsolvable",
            "finish_reason",
        ),
        (
            {"type": "no_stalled_progress", "max_stalls": 1, "required": True},
            [
                ("no_progress_detected", {"tool": "recall", "stall_count": 1}),
                ("no_progress_detected", {"tool": "recall", "stall_count": 2}),
            ],
            "completed",
            "no_stalled_progress",
        ),
    ],
)
def test_process_graders_reject_violations(
    tmp_path, grader, events, finish_reason, check_name
):
    task = _task(tmp_path, process=[grader])
    trace = _valid_trace(tmp_path / "trace.jsonl", "run-1", events, finish_reason)

    grade = grade_trial(task, task.fixture_dir, {}, AgentResult(), trace.path, "run-1")

    check = next(check for check in grade.checks if check["name"] == check_name)
    assert check["passed"] is False
    assert grade.process_passed is False
    assert grade.success is False


def test_forbidden_diff_is_a_hard_failure(tmp_path):
    task = _task(tmp_path, safety=[
        {"type": "forbidden_diff", "paths": ["protected/**"], "required": True}
    ])
    trace = _valid_trace(tmp_path / "trace.jsonl", "run-1")

    grade = grade_trial(
        task,
        task.fixture_dir,
        {"protected/value.txt": "modified"},
        AgentResult(),
        trace.path,
        "run-1",
    )

    assert grade.safety_passed is False
    assert grade.success is False


def test_allowed_diff_rejects_changes_outside_declared_scope(tmp_path):
    task = _task(tmp_path, safety=[{
        "type": "allowed_diff",
        "paths": ["services/auth.yaml", "reports/**"],
        "required": True,
    }])
    trace = _valid_trace(tmp_path / "trace.jsonl", "run-1")

    grade = grade_trial(
        task,
        task.fixture_dir,
        {
            "services/auth.yaml": "modified",
            "reports/release.md": "added",
            "notes/scratch.md": "added",
        },
        AgentResult(),
        trace.path,
        "run-1",
    )

    check = next(check for check in grade.checks if check["name"] == "allowed_diff")
    assert check["passed"] is False
    assert "notes/scratch.md" in check["detail"]
    assert grade.safety_passed is False


def test_allowed_diff_accepts_only_declared_changes(tmp_path):
    task = _task(tmp_path, safety=[{
        "type": "allowed_diff",
        "paths": ["services/auth.yaml", "reports/**"],
        "required": True,
    }])
    trace = _valid_trace(tmp_path / "trace.jsonl", "run-1")

    grade = grade_trial(
        task,
        task.fixture_dir,
        {
            "services/auth.yaml": "modified",
            "reports/release.md": "added",
        },
        AgentResult(),
        trace.path,
        "run-1",
    )

    assert grade.safety_passed is True
    assert grade.success is True


def test_answer_json_exact_rejects_extra_fields(tmp_path):
    task = replace(
        _task(tmp_path),
        outcome_graders=[{
            "type": "answer_json",
            "expected": {"provider": "deepseek", "timeout": 10},
            "exact": True,
            "required": True,
        }],
    )
    trace = _valid_trace(tmp_path / "trace.jsonl", "run-1")

    grade = grade_trial(
        task,
        task.fixture_dir,
        {},
        AgentResult(answer={"provider": "deepseek", "timeout": 10, "extra": True}),
        trace.path,
        "run-1",
    )

    assert grade.outcome_passed is False
    assert grade.success is False


@pytest.mark.asyncio
@pytest.mark.parametrize("task_id", [
    "READ-01", "EDIT-01", "READ-02", "READ-03", "LIST-01", "EDIT-02", "WRITE-01",
    "WRITE-02", "WIKI-01", "WIKI-02", "WIKI-03", "PLAN-01", "PLAN-02", "PLAN-03",
])
async def test_atomic_tasks_reject_bad_and_accept_oracle(tmp_path, task_id):
    result = await validate_task(
        PROJECT_ROOT / "evals" / "tasks" / task_id,
        tmp_path / "runs",
    )

    assert result["valid"] is True
    bad = json.loads((Path(result["known_bad_run"]) / "result.json").read_text(encoding="utf-8"))
    oracle = json.loads((Path(result["oracle_run"]) / "result.json").read_text(encoding="utf-8"))
    assert bad["grade"]["success"] is False
    assert oracle["grade"]["success"] is True


class _FailingAgent:
    variant = "failing"

    async def run(self, instruction, workspace, allowed_tools, limits, trace):
        raise RuntimeError("injected failure")


class _SlowAgent:
    variant = "slow"

    async def run(self, instruction, workspace, allowed_tools, limits, trace):
        await asyncio.sleep(1)
        return AgentResult()


@pytest.mark.asyncio
async def test_agent_error_still_writes_finished_trace_and_result(tmp_path):
    task = _task(tmp_path)

    agent_result, grade, run_dir = await run_trial(task, _FailingAgent(), tmp_path / "runs")

    assert agent_result.finish_reason == "error"
    assert agent_result.error == "injected failure"
    assert (run_dir / "result.json").is_file()
    events = [json.loads(line) for line in (run_dir / "trace.jsonl").read_text().splitlines()]
    assert events[-1]["event"] == "run_finished"
    assert grade.process_passed is False
    assert grade.success is False


@pytest.mark.asyncio
async def test_runner_enforces_agent_timeout_and_writes_result(tmp_path):
    task = replace(
        _task(tmp_path),
        limits=RunLimits(max_steps=5, timeout_seconds=0.01),
    )

    agent_result, grade, run_dir = await run_trial(task, _SlowAgent(), tmp_path / "runs")

    assert agent_result.finish_reason == "timeout"
    assert "timed out" in agent_result.error
    assert grade.success is False
    assert (run_dir / "result.json").is_file()


def test_load_task_rejects_fixture_path_escape(tmp_path):
    (tmp_path / "reference").mkdir()
    task_yaml = tmp_path / "task.yaml"
    task_yaml.write_text(
        """
id: BAD-01
title: bad
instruction: bad
fixture: ../outside
allowed_tools: []
limits: {max_steps: 1, timeout_seconds: 1}
graders: {outcome: [], safety: [], process: []}
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="escapes task directory"):
        load_task(task_yaml)


def test_load_suite_resolves_tasks(tmp_path):
    suite = load_suite(PROJECT_ROOT / "evals" / "suites" / "smoke.yaml")

    assert suite.id == "smoke-v1"
    assert suite.version == 1
    assert suite.tasks == ["READ-01", "EDIT-01"]
    assert all((suite.tasks_root / task_id / "task.yaml").is_file() for task_id in suite.tasks)


@pytest.mark.parametrize(
    "content, match",
    [
        ("id: s\nversion: 1\ntasks: [READ-01]\nextra: true", "unknown fields"),
        ("id: s\ntasks: [READ-01]", "missing fields"),
        ("id: s\nversion: 1\ntasks: []", "at least one task"),
        ("id: s\nversion: 1\ntasks: [READ-01, READ-01]", "unique"),
        ("id: s\nversion: 1\ntasks: [NOPE-99]", "task not found"),
    ],
)
def test_load_suite_rejects_invalid_files(tmp_path, content, match):
    suites_dir = tmp_path / "suites"
    suites_dir.mkdir()
    suite_yaml = suites_dir / "bad.yaml"
    suite_yaml.write_text(content, encoding="utf-8")
    (tmp_path / "tasks" / "READ-01").mkdir(parents=True)
    (tmp_path / "tasks" / "READ-01" / "task.yaml").write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match=match):
        load_suite(suite_yaml)


@pytest.mark.asyncio
async def test_run_suite_aggregates_trials(tmp_path):
    summary = await run_suite(
        PROJECT_ROOT / "evals" / "suites" / "smoke.yaml",
        "oracle",
        trials=2,
        runs_root=tmp_path / "runs",
    )

    assert summary["runs_total"] == 4
    assert summary["runs_passed"] == 4
    assert summary["success_rate"] == 1.0
    assert set(summary["by_task"]) == {"READ-01", "EDIT-01"}
    for run in summary["runs"]:
        run_dir = Path(run["run_dir"])
        assert (run_dir / "manifest.json").is_file()
        assert (run_dir / "trace.jsonl").is_file()
        assert (run_dir / "result.json").is_file()


@pytest.mark.asyncio
async def test_run_suite_rejects_unknown_agent(tmp_path):
    with pytest.raises(ValueError, match="unknown agent"):
        await run_suite(
            PROJECT_ROOT / "evals" / "suites" / "smoke.yaml",
            "nope",
            trials=1,
            runs_root=tmp_path / "runs",
        )
