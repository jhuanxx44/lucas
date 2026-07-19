from dataclasses import dataclass
from pathlib import Path
from typing import Callable

TOOL_STATUSES = {"ok", "invalid_input", "denied", "timeout", "error"}

ToolHandler = Callable[[Path, dict], "ToolResult"]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    args_description: str
    handler: ToolHandler


@dataclass
class ToolResult:
    status: str
    observation: str = ""
    error_code: str = ""
    duration_ms: float = 0.0
    truncated: bool = False

    def __post_init__(self):
        if self.status not in TOOL_STATUSES:
            raise ValueError(f"unknown tool status: {self.status}")

    @property
    def ok(self) -> bool:
        return self.status == "ok"
