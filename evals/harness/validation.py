from pathlib import Path

from evals.harness.adapters.oracle import OracleAgent
from evals.harness.models import AgentResult, RunLimits, load_task
from evals.harness.runner import run_trial
from evals.harness.trace import TraceRecorder


class _KnownBadAgent:
    variant = "known-bad"

    async def run(
        self,
        instruction: str,
        workspace: Path,
        allowed_tools: list[str],
        limits: RunLimits,
        trace: TraceRecorder,
    ) -> AgentResult:
        trace.record("step_started", {"step_id": "bad-1", "name": "return wrong result"})
        trace.record("step_finished", {"step_id": "bad-1"})
        return AgentResult(answer={}, finish_reason="completed")


async def validate_task(task_path: str | Path, runs_root: Path) -> dict:
    task = load_task(task_path)
    _, bad_grade, bad_run = await run_trial(task, _KnownBadAgent(), runs_root)
    if bad_grade.success:
        raise ValueError("known-bad trial unexpectedly passed required graders")

    _, oracle_grade, oracle_run = await run_trial(
        task,
        OracleAgent(
            task.reference_dir,
            tool_name="write_file" if "write_file" in task.allowed_tools else "apply_patch",
        ),
        runs_root,
    )
    if not oracle_grade.success:
        failed = [
            check for check in oracle_grade.checks
            if check["required"] and not check["passed"]
        ]
        raise ValueError(f"Oracle failed required graders: {failed}")
    return {
        "task_id": task.id,
        "valid": True,
        "known_bad_run": str(bad_run),
        "oracle_run": str(oracle_run),
    }
