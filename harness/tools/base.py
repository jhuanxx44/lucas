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
    parameters: dict
    handler: ToolHandler

    def __post_init__(self) -> None:
        """尽早拒绝无法作为 function tool 参数使用的基础 schema。"""
        if self.parameters.get("type") != "object":
            raise ValueError(f"tool {self.name} parameters must be an object schema")
        properties = self.parameters.get("properties")
        if not isinstance(properties, dict):
            raise ValueError(f"tool {self.name} parameters.properties must be an object")
        required = self.parameters.get("required")
        if not isinstance(required, list) or not all(isinstance(key, str) for key in required):
            raise ValueError(f"tool {self.name} parameters.required must be a string list")
        unknown_required = set(required) - set(properties)
        if unknown_required:
            raise ValueError(
                f"tool {self.name} required properties are undefined: {sorted(unknown_required)}"
            )
        if self.parameters.get("additionalProperties") is not False:
            raise ValueError(f"tool {self.name} parameters must forbid additional properties")


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
