"""update_plan 哑工具：harness 不保存/校验 plan 状态，只把 plan 全文回显到 observation。"""
from pathlib import Path

from harness.tools.base import ToolResult, ToolSpec


def _update_plan(workspace: Path, args: dict) -> ToolResult:
    # 宽容解析：模型可能传 steps（正确）、plan（Codex 式）、或字符串
    steps = args.get("steps", args.get("plan", []))
    # plan 字段可能是字符串（模型凭记忆把计划写成一段话），此时转为单步
    if isinstance(steps, str):
        steps = [{"step": steps, "status": "in_progress"}]
    if not isinstance(steps, list):
        return ToolResult(status="invalid_input", error_code="bad_args",
                          observation="steps/plan must be a list or string")
    lines = ["## 当前计划"]
    for i, s in enumerate(steps):
        if isinstance(s, str):
            s = {"step": s}
        if not isinstance(s, dict):
            return ToolResult(status="invalid_input", error_code="bad_args",
                              observation=f"steps[{i}] must be an object or string")
        step_text = s.get("step", "")
        status = s.get("status", "pending")
        if status not in ("pending", "in_progress", "completed"):
            status = "pending"
        emoji = {"pending": "⬜", "in_progress": "🔵", "completed": "✅"}.get(status, "⬜")
        lines.append(f"- {emoji} {step_text}")
    return ToolResult(status="ok", observation="\n".join(lines))


UPDATE_PLAN_SPEC = ToolSpec(
    name="update_plan",
    description="更新执行计划。仅当面对需要多步骤、多工具的复杂任务时使用。简单任务不要调用此工具。参数 steps 为步骤列表，每项含 step（步骤描述）与 status（pending|in_progress|completed）。调用后，你的下一条消息应开始执行第一个 pending/in_progress 步骤。若传入 plan（字符串或列表）也会被接受。",
    args_description="steps: 步骤列表，每项含 step (string) 与 status (string, 可选，默认 pending)。也接受 plan 字段（字符串或列表）。",
    handler=_update_plan,
)
