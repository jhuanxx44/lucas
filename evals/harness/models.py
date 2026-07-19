from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

# RunLimits/AgentResult/TraceEvent 已上移至 harness.models，此处 re-export 保持向后兼容
from harness.models import AgentResult, RunLimits, TraceEvent

__all__ = [
    "AgentResult", "GradeResult", "RunLimits", "SuiteSpec", "TaskSpec",
    "TraceEvent", "Trial", "load_suite", "load_task",
]


@dataclass(frozen=True)
class TaskSpec:
    id: str
    title: str
    instruction: str
    fixture: str
    allowed_tools: list[str]
    limits: RunLimits
    outcome_graders: list[dict]
    safety_graders: list[dict]
    process_graders: list[dict]
    tags: list[str]
    task_dir: Path = field(repr=False, compare=False)

    @property
    def fixture_dir(self) -> Path:
        return _child_path(self.task_dir, self.fixture)

    @property
    def reference_dir(self) -> Path:
        return self.task_dir / "reference"


@dataclass(frozen=True)
class SuiteSpec:
    id: str
    version: int
    tasks: list[str]
    suite_path: Path = field(repr=False, compare=False)

    @property
    def tasks_root(self) -> Path:
        return self.suite_path.parent.parent / "tasks"


@dataclass(frozen=True)
class Trial:
    run_id: str
    task_id: str
    agent_variant: str
    trial_index: int
    workspace: str
    started_at: str


@dataclass
class GradeResult:
    success: bool
    outcome_passed: bool
    safety_passed: bool
    process_passed: bool
    checks_passed: int
    checks_total: int
    checks: list[dict]

    def to_dict(self) -> dict:
        return asdict(self)


def load_task(task_path: str | Path) -> TaskSpec:
    path = Path(task_path).resolve()
    if path.is_dir():
        path = path / "task.yaml"
    if not path.is_file():
        raise ValueError(f"task.yaml not found: {path}")

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("task.yaml must contain a mapping")

    required = {"id", "title", "instruction", "fixture", "allowed_tools", "limits", "graders"}
    missing = sorted(required - raw.keys())
    if missing:
        raise ValueError(f"task.yaml missing fields: {', '.join(missing)}")

    limits_raw = raw["limits"]
    graders = raw["graders"]
    if not isinstance(limits_raw, dict) or not isinstance(graders, dict):
        raise ValueError("limits and graders must be mappings")

    limits = RunLimits(
        max_steps=_positive_int(limits_raw.get("max_steps"), "limits.max_steps"),
        timeout_seconds=_positive_number(
            limits_raw.get("timeout_seconds"), "limits.timeout_seconds"
        ),
        max_cost_usd=float(limits_raw.get("max_cost_usd", 0.0)),
    )
    task = TaskSpec(
        id=str(raw["id"]),
        title=str(raw["title"]),
        instruction=str(raw["instruction"]),
        fixture=str(raw["fixture"]),
        allowed_tools=_string_list(raw["allowed_tools"], "allowed_tools"),
        limits=limits,
        outcome_graders=_grader_list(graders.get("outcome", []), "outcome"),
        safety_graders=_grader_list(graders.get("safety", []), "safety"),
        process_graders=_grader_list(graders.get("process", []), "process"),
        tags=_string_list(raw.get("tags", []), "tags"),
        task_dir=path.parent,
    )
    if not task.fixture_dir.is_dir():
        raise ValueError(f"fixture directory not found: {task.fixture_dir}")
    if not task.reference_dir.is_dir():
        raise ValueError(f"reference directory not found: {task.reference_dir}")
    _reject_symlinks(task.fixture_dir)
    _reject_symlinks(task.reference_dir)
    return task


def load_suite(suite_path: str | Path) -> SuiteSpec:
    path = Path(suite_path).resolve()
    if path.is_dir():
        path = path / "suite.yaml"
    if not path.is_file():
        raise ValueError(f"suite file not found: {path}")

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("suite file must contain a mapping")

    allowed = {"id", "version", "tasks"}
    unknown = sorted(raw.keys() - allowed)
    if unknown:
        raise ValueError(f"suite file has unknown fields: {', '.join(unknown)}")
    missing = sorted(allowed - raw.keys())
    if missing:
        raise ValueError(f"suite file missing fields: {', '.join(missing)}")

    suite = SuiteSpec(
        id=str(raw["id"]),
        version=_positive_int(raw["version"], "version"),
        tasks=_string_list(raw["tasks"], "tasks"),
        suite_path=path,
    )
    if not suite.tasks:
        raise ValueError("suite must contain at least one task")
    if len(set(suite.tasks)) != len(suite.tasks):
        raise ValueError("suite tasks must be unique")
    for task_id in suite.tasks:
        task_dir = suite.tasks_root / task_id
        if not (task_dir / "task.yaml").is_file():
            raise ValueError(f"suite task not found: {task_dir}")
    return suite


def _child_path(parent: Path, child: str) -> Path:
    candidate = (parent / child).resolve()
    if candidate != parent and parent not in candidate.parents:
        raise ValueError(f"path escapes task directory: {child}")
    return candidate


def _positive_int(value: Any, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _positive_number(value: Any, name: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{name} must be a positive number")
    return float(value)


def _string_list(value: Any, name: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{name} must be a list of strings")
    return value


def _grader_list(value: Any, name: str) -> list[dict]:
    if not isinstance(value, list) or any(
        not isinstance(item, dict) or not isinstance(item.get("type"), str)
        for item in value
    ):
        raise ValueError(f"graders.{name} must be a list of grader mappings")
    return value


def _reject_symlinks(root: Path):
    if any(path.is_symlink() for path in root.rglob("*")):
        raise ValueError(f"symlinks are not allowed in task data: {root}")
