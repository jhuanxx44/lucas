import asyncio
import json
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from evals.harness.adapters.base import AgentAdapter
from evals.harness.grader import grade_trial
from evals.harness.models import AgentResult, GradeResult, TaskSpec, Trial
from evals.harness.trace import TraceRecorder
from evals.harness.workspace import TrialWorkspace


async def run_trial(
    task: TaskSpec,
    adapter: AgentAdapter,
    runs_root: Path,
    trial_index: int = 0,
) -> tuple[AgentResult, GradeResult, Path]:
    started_at = datetime.now(timezone.utc).isoformat()
    run_id = f"{task.id.lower()}-{uuid.uuid4().hex[:12]}"
    run_dir = runs_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    workspace = TrialWorkspace(task.fixture_dir)
    trial = Trial(
        run_id=run_id,
        task_id=task.id,
        agent_variant=adapter.variant,
        trial_index=trial_index,
        workspace=str(workspace.root),
        started_at=started_at,
    )
    _write_json(run_dir / "manifest.json", {
        **asdict(trial),
        "allowed_tools": task.allowed_tools,
        "limits": asdict(task.limits),
    })
    trace = TraceRecorder(run_dir / "trace.jsonl", run_id)
    trace.record("run_started", {"task_id": task.id, "agent_variant": adapter.variant})

    try:
        agent_result = await asyncio.wait_for(
            adapter.run(
                task.instruction,
                workspace.root,
                task.allowed_tools,
                task.limits,
                trace,
            ),
            timeout=task.limits.timeout_seconds,
        )
    except TimeoutError:
        message = f"agent timed out after {task.limits.timeout_seconds}s"
        agent_result = AgentResult(finish_reason="timeout", error=message)
        trace.record("agent_error", {"message": message, "error_type": "timeout"})
    except Exception as e:
        agent_result = AgentResult(finish_reason="error", error=str(e))
        trace.record("agent_error", {"message": str(e)})
    trace.record("run_finished", {
        "finish_reason": agent_result.finish_reason,
        "error": agent_result.error,
    })

    changes = workspace.changes()
    grade = grade_trial(
        task, workspace.root, changes, agent_result, trace.path, run_id
    )
    workspace.archive_to(run_dir / "workspace")
    _write_json(run_dir / "result.json", {
        "agent_result": asdict(agent_result),
        "grade": grade.to_dict(),
        "changes": changes,
    })
    workspace.cleanup()
    return agent_result, grade, run_dir


def _write_json(path: Path, value: dict):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
