import json
from pathlib import Path

from evals.harness.models import AgentResult, RunLimits
from evals.harness.trace import TraceRecorder
from harness.model_adapter import ModelAdapter
from harness.models import StepContext
from harness.tools.registry import ToolRuntime

MAX_OBSERVATION_CHARS = 4000


def load_prompt_template(path: str | Path) -> str:
    """加载 prompt 模板并剥离 frontmatter（--- ... ---）"""
    text = Path(path).read_text(encoding="utf-8")
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[end + 4:].lstrip("\n")
    return text


class AgentRunner:
    """通用最小 Agent 循环：模型每轮返回一个 JSON（tool 或 answer）"""

    def __init__(self, model: ModelAdapter, tools: ToolRuntime, prompt_template: str):
        self.model = model
        self.tools = tools
        self.prompt_template = prompt_template

    async def run(
        self,
        instruction: str,
        allowed_tools: list[str],
        limits: RunLimits,
        trace: TraceRecorder,
    ) -> AgentResult:
        context = StepContext(step_id="", instruction=instruction)
        last_failed_signature = None
        for step in range(1, limits.max_steps + 1):
            context.step_id = f"step-{step}"
            trace.record("step_started", {"step_id": context.step_id})
            prompt = self._render(context, allowed_tools)
            raw = await self.model.complete(prompt)
            action = _parse_action(raw)
            if action is None:
                context.observations.append(
                    "你的上一条回复不是合法 JSON。请只返回一个 JSON 对象："
                    '{"action": "tool", ...} 或 {"action": "answer", ...}'
                )
                trace.record("step_finished", {"step_id": context.step_id})
                continue

            if action["kind"] == "answer":
                trace.record("step_finished", {"step_id": context.step_id})
                return AgentResult(answer=action["answer"], finish_reason="completed")

            tool, args = action["tool"], action["args"]
            signature = (tool, json.dumps(args, sort_keys=True, ensure_ascii=False))
            if signature == last_failed_signature:
                trace.record("step_finished", {"step_id": context.step_id})
                return AgentResult(
                    finish_reason="error",
                    error=f"repeated failing tool call aborted: {tool}",
                )
            call_id = f"call-{step}"
            trace.record("tool_call_started", {
                "tool_call_id": call_id, "tool": tool, "args": args,
            })
            result = self.tools.execute(tool, args, allowed_tools)
            if result.ok:
                trace.record("tool_call_finished", {"tool_call_id": call_id})
                last_failed_signature = None
            else:
                trace.record("tool_call_error", {
                    "tool_call_id": call_id,
                    "status": result.status,
                    "error_code": result.error_code,
                })
                last_failed_signature = signature
            context.observations.append(_format_observation(tool, result))
            trace.record("step_finished", {"step_id": context.step_id})
        return AgentResult(finish_reason="max_steps", error="max steps exhausted")

    def _render(self, context: StepContext, allowed_tools: list[str]) -> str:
        observations = "\n\n".join(context.observations) or "（暂无）"
        return self.prompt_template.format(
            instruction=context.instruction,
            tools_desc=self.tools.describe(allowed_tools),
            observations=observations,
        )


def _parse_action(raw: str) -> dict | None:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]) if len(lines) >= 2 else text.strip("`")
    try:
        value = json.loads(text.strip())
    except json.JSONDecodeError:
        return None
    if not isinstance(value, dict):
        return None
    if value.get("action") == "answer":
        answer = value.get("reply", value.get("answer"))
        if answer is None:
            return None
        return {"kind": "answer", "answer": answer}
    if value.get("action") == "tool" and isinstance(value.get("tool"), str):
        args = value.get("args", {})
        if not isinstance(args, dict):
            return None
        return {"kind": "tool", "tool": value["tool"], "args": args}
    return None


def _format_observation(tool: str, result) -> str:
    observation = result.observation
    truncated = result.truncated
    if len(observation) > MAX_OBSERVATION_CHARS:
        observation = observation[:MAX_OBSERVATION_CHARS]
        truncated = True
    suffix = " [truncated]" if truncated else ""
    return f"[{tool}] status={result.status}{suffix}\n{observation}"
