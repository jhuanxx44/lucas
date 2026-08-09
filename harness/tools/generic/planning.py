"""update_plan tool: echo a canonical native-tool plan as an observation."""

from pathlib import Path

from harness.tools.base import ToolResult, ToolSpec


def _update_plan(workspace: Path, args: dict) -> ToolResult:
    steps = args.get("steps")
    if not isinstance(steps, list):
        return ToolResult(
            status="invalid_input",
            error_code="bad_args",
            observation="steps must be a list",
        )
    lines = ["## 当前计划"]
    for index, item in enumerate(steps):
        if not isinstance(item, dict):
            return ToolResult(
                status="invalid_input",
                error_code="bad_args",
                observation=f"steps[{index}] must be an object",
            )
        step_text = item.get("step", "")
        status = item.get("status", "pending")
        if status not in ("pending", "in_progress", "completed"):
            status = "pending"
        emoji = {"pending": "⬜", "in_progress": "🔵", "completed": "✅"}[status]
        lines.append(f"- {emoji} {step_text}")
    return ToolResult(status="ok", observation="\n".join(lines))


UPDATE_PLAN_SPEC = ToolSpec(
    name="update_plan",
    description=(
        "更新执行计划。仅当面对需要多步骤、多工具的复杂任务时使用。"
        "简单任务不要调用此工具。每项包含 step 和 status；调用后开始执行第一个"
        " pending/in_progress 步骤。写入类工具串行执行，一次一个，不会与同批其他写入并发。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "steps": {
                "type": "array",
                "description": "执行步骤列表",
                "items": {
                    "type": "object",
                    "properties": {
                        "step": {
                            "type": "string",
                            "minLength": 1,
                            "description": "步骤描述",
                        },
                        "status": {
                            "type": "string",
                            "enum": ["pending", "in_progress", "completed"],
                            "default": "pending",
                        },
                    },
                    "required": ["step"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["steps"],
        "additionalProperties": False,
    },
    handler=_update_plan,
)
