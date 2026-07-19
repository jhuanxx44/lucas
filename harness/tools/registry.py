import time
from pathlib import Path

from harness.tools.base import ToolResult, ToolSpec


class ToolRuntime:
    """工具注册表：按 allowed_tools 过滤，统一执行入口"""

    def __init__(self, workspace: Path, specs: list[ToolSpec]):
        self.workspace = workspace
        self._specs = {spec.name: spec for spec in specs}

    def available(self, allowed_tools: list[str]) -> list[ToolSpec]:
        return [self._specs[name] for name in allowed_tools if name in self._specs]

    def describe(self, allowed_tools: list[str]) -> str:
        lines = []
        for spec in self.available(allowed_tools):
            lines.append(f"- {spec.name}: {spec.description}\n  参数: {spec.args_description}")
        return "\n".join(lines) if lines else "（无可用工具）"

    def execute(self, name: str, args: dict, allowed_tools: list[str]) -> ToolResult:
        spec = self._specs.get(name)
        if spec is None:
            return ToolResult(status="invalid_input", error_code="unknown_tool",
                              observation=f"unknown tool: {name}")
        if name not in allowed_tools:
            return ToolResult(status="denied", error_code="tool_not_allowed",
                              observation=f"tool not allowed in this task: {name}")
        if not isinstance(args, dict):
            return ToolResult(status="invalid_input", error_code="bad_args",
                              observation="args must be a JSON object")
        start = time.monotonic()
        try:
            result = spec.handler(self.workspace, args)
        except Exception as e:
            result = ToolResult(status="error", error_code="handler_exception",
                                observation=f"{type(e).__name__}: {e}")
        result.duration_ms = result.duration_ms or (time.monotonic() - start) * 1000
        return result
