from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable

TOOL_STATUSES = {"ok", "invalid_input", "denied", "timeout", "error"}

# handler 可以是同步或 async；ToolRuntime.execute 统一 await 兼容两者
ToolHandler = Callable[[Path, dict], "ToolResult | Awaitable[ToolResult]"]


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
