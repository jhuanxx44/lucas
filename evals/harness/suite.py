import json
import uuid
from pathlib import Path

from evals.harness.adapters.base import AgentAdapter
from evals.harness.adapters.lucas_single import LucasSingleAgent
from evals.harness.adapters.oracle import OracleAgent
from evals.harness.models import TaskSpec, load_suite, load_task
from evals.harness.runner import run_trial


def build_adapter(name: str, task: TaskSpec) -> AgentAdapter:
    if name == "oracle":
        return OracleAgent(task.reference_dir)
    if name == "lucas-single":
        return LucasSingleAgent()
    raise ValueError(f"unknown agent: {name}")


async def run_suite(
    suite_path: str | Path,
    agent: str,
    trials: int,
    runs_root: Path,
) -> dict:
    if trials < 1:
        raise ValueError("trials must be a positive integer")
    suite = load_suite(suite_path)
    suite_run_id = f"{suite.id.lower()}-{uuid.uuid4().hex[:8]}"
    suite_dir = runs_root / suite_run_id
    suite_dir.mkdir(parents=True, exist_ok=False)

    runs = []
    for task_id in suite.tasks:
        task = load_task(suite.tasks_root / task_id)
        for trial_index in range(trials):
            agent_result, grade, run_dir = await run_trial(
                task,
                build_adapter(agent, task),
                suite_dir / "runs",
                trial_index,
            )
            runs.append({
                "task_id": task.id,
                "trial_index": trial_index,
                "run_dir": str(run_dir),
                "finish_reason": agent_result.finish_reason,
                "success": grade.success,
                "outcome_passed": grade.outcome_passed,
                "safety_passed": grade.safety_passed,
                "process_passed": grade.process_passed,
            })

    passed = sum(1 for run in runs if run["success"])
    by_task = {
        task_id: {
            "runs": sum(1 for run in runs if run["task_id"] == task_id),
            "passed": sum(
                1 for run in runs if run["task_id"] == task_id and run["success"]
            ),
        }
        for task_id in suite.tasks
    }
    summary = {
        "suite_id": suite.id,
        "suite_version": suite.version,
        "agent": agent,
        "trials_per_task": trials,
        "runs_total": len(runs),
        "runs_passed": passed,
        "success_rate": passed / len(runs),
        "by_task": by_task,
        "runs": runs,
    }
    (suite_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary
