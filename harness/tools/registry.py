import inspect
import time
from pathlib import Path

from harness.tools.base import ToolResult, ToolSpec


def _schema_error(value, schema: dict, path: str = "args") -> str:
    if "enum" in schema and value not in schema["enum"]:
        return f"{path} must be one of {schema['enum']}"
    expected = schema.get("type")
    matches = {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
    }
    if expected in matches and not matches[expected]:
        return f"{path} must be {expected}"
    if expected == "object":
        properties = schema.get("properties", {})
        missing = [key for key in schema.get("required", []) if key not in value]
        if missing:
            return f"{path} missing required properties: {missing}"
        if schema.get("additionalProperties") is False:
            unknown = sorted(set(value) - set(properties))
            if unknown:
                return f"{path} has unknown properties: {unknown}"
        for key, item in value.items():
            if key in properties:
                error = _schema_error(item, properties[key], f"{path}.{key}")
                if error:
                    return error
    elif expected == "array":
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                error = _schema_error(item, item_schema, f"{path}[{index}]")
                if error:
                    return error
    elif expected == "string" and len(value) < schema.get("minLength", 0):
        return f"{path} is too short"
    elif expected in ("integer", "number"):
        if "minimum" in schema and value < schema["minimum"]:
            return f"{path} must be >= {schema['minimum']}"
        if "maximum" in schema and value > schema["maximum"]:
            return f"{path} must be <= {schema['maximum']}"
    return ""


class ToolRuntime:
    """工具注册表：按 allowed_tools 过滤，统一执行入口"""

    def __init__(self, workspace: Path, specs: list[ToolSpec]):
        self.workspace = workspace
        self._specs = {spec.name: spec for spec in specs}

    def available(self, allowed_tools: list[str]) -> list[ToolSpec]:
        return [self._specs[name] for name in allowed_tools if name in self._specs]

    async def execute(self, name: str, args: dict, allowed_tools: list[str]) -> ToolResult:
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
        schema_error = _schema_error(args, spec.parameters)
        if schema_error:
            return ToolResult(
                status="invalid_input",
                error_code="schema_validation",
                observation=schema_error,
            )
        start = time.monotonic()
        try:
            result = spec.handler(self.workspace, args)
            if inspect.isawaitable(result):
                result = await result
            if not isinstance(result, ToolResult):
                raise TypeError("tool handler must return ToolResult")
        except Exception as e:
            result = ToolResult(status="error", error_code="handler_exception",
                                observation=f"{type(e).__name__}: {e}")
        result.duration_ms = result.duration_ms or (time.monotonic() - start) * 1000
        return result
