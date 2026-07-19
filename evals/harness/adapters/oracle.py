import json
import shutil
from pathlib import Path

from evals.harness.models import AgentResult, RunLimits
from evals.harness.trace import TraceRecorder


class OracleAgent:
    variant = "oracle"

    def __init__(self, reference_dir: Path, tool_name: str = "apply_patch"):
        self.reference_dir = reference_dir
        self.tool_name = tool_name

    async def run(
        self,
        instruction: str,
        workspace: Path,
        allowed_tools: list[str],
        limits: RunLimits,
        trace: TraceRecorder,
    ) -> AgentResult:
        trace.record("step_started", {"step_id": "oracle-1", "name": "apply reference"})
        answer = None
        answer_path = self.reference_dir / "answer.json"
        if answer_path.is_file():
            answer = json.loads(answer_path.read_text(encoding="utf-8"))

        reference_workspace = self.reference_dir / "workspace"
        if reference_workspace.is_dir():
            for index, source in enumerate(sorted(reference_workspace.rglob("*")), 1):
                if not source.is_file():
                    continue
                relative = source.relative_to(reference_workspace)
                destination = workspace / relative
                call_id = f"oracle-tool-{index}"
                trace.record("tool_call_started", {
                    "tool_call_id": call_id,
                    "tool": self.tool_name,
                    "args": {"path": relative.as_posix()},
                })
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
                trace.record("tool_call_finished", {"tool_call_id": call_id})
        trace.record("step_finished", {"step_id": "oracle-1"})
        return AgentResult(answer=answer, finish_reason="completed")
