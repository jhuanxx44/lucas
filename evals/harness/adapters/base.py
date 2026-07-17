from pathlib import Path
from typing import Protocol

from evals.harness.models import AgentResult, RunLimits
from evals.harness.trace import TraceRecorder


class AgentAdapter(Protocol):
    variant: str

    async def run(
        self,
        instruction: str,
        workspace: Path,
        allowed_tools: list[str],
        limits: RunLimits,
        trace: TraceRecorder,
    ) -> AgentResult: ...
