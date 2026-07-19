import json
import time
from pathlib import Path

from harness.model_adapter import ModelAdapter
from harness.models import AgentResult, RunLimits, StepContext
from harness.tools.registry import ToolRuntime
from harness.trace import TraceRecorder
from utils.token_tracker import TokenUsage


class _NullTrace:
    """trace 为空时的 no-op 替代，保持 Runner 主循环不做分支判断"""

    def record(self, event: str, data: dict | None = None) -> None:
        return None


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
        trace: TraceRecorder | None = None,
    ) -> AgentResult:
        context = StepContext(step_id="", instruction=instruction)
        last_failed_signature = None
        total_observation_chars = 0
        total_usage: TokenUsage | None = None
        cost_usd = 0.0
        artifacts: Path | None = None
        if trace is not None:
            artifacts = trace.path.parent / "artifacts"
            artifacts.mkdir(exist_ok=True)
        else:
            trace = _NullTrace()
        for step in range(1, limits.max_steps + 1):
            context.step_id = f"step-{step}"
            trace.record("step_started", {"step_id": context.step_id})
            prompt = self._render(context, allowed_tools)
            # 大 payload 写 artifact，trace 只留引用；prompt 不含敏感信息（工作区隔离、env 已净化）
            prompt_ref = (
                _write_artifact(artifacts, f"prompt-{context.step_id}.txt", prompt)
                if artifacts is not None else None
            )
            trace.record("prompt_rendered", {
                "step_id": context.step_id,
                "prompt_chars": len(prompt),
                "artifact": prompt_ref,
            })
            trace.record("model_call_started", {
                "step_id": context.step_id, "model_call_id": f"model-{step}",
            })
            started = time.monotonic()
            raw, usage = await self.model.complete(prompt)
            duration_ms = (time.monotonic() - started) * 1000
            if usage is not None:
                total_usage = usage if total_usage is None else total_usage.merge(usage)
            cost_usd = total_usage.total_cost if total_usage is not None else 0.0
            output_ref = (
                _write_artifact(artifacts, f"output-{context.step_id}.txt", raw)
                if artifacts is not None else None
            )
            trace.record("model_call_finished", {
                "step_id": context.step_id,
                "model_call_id": f"model-{step}",
                "duration_ms": round(duration_ms, 1),
                "output_chars": len(raw),
                "artifact": output_ref,
                **(_usage_trace_data(usage)),
            })
            # 全量回放：模型自己的原始输出（包括格式错误的）进入后续上下文
            context.history.append({"role": "assistant", "content": raw})
            action = _parse_action(raw)
            if action is None:
                trace.record("action_parsed", {
                    "step_id": context.step_id, "kind": "invalid",
                })
                context.history.append({"role": "tool", "content": (
                    "你的上一条回复格式不对。请返回且只返回一个 JSON 对象："
                    '调用工具用 {"action": "tool", "tool": "工具名", "args": {...}}；'
                    '最终作答用 {"action": "answer", "reply": "答案"}。'
                    "如果答案本身是 JSON，请把它作为 reply 的字符串值或直接用其内容作答。"
                )})
                trace.record("step_finished", {"step_id": context.step_id})
                continue

            if action["kind"] == "answer":
                answer_text = action["answer"]
                trace.record("action_parsed", {
                    "step_id": context.step_id,
                    "kind": "answer",
                    "answer_preview": str(answer_text)[:500],
                })
                trace.record("step_finished", {"step_id": context.step_id})
                return AgentResult(
                    answer=answer_text, finish_reason="completed",
                    usage=total_usage, cost_usd=cost_usd,
                )

            tool, args = action["tool"], action["args"]
            trace.record("action_parsed", {
                "step_id": context.step_id, "kind": "tool", "tool": tool, "args": args,
            })
            signature = (tool, json.dumps(args, sort_keys=True, ensure_ascii=False))
            if signature == last_failed_signature:
                trace.record("step_finished", {"step_id": context.step_id})
                return AgentResult(
                    finish_reason="error",
                    error=f"repeated failing tool call aborted: {tool}",
                    usage=total_usage, cost_usd=cost_usd,
                )
            # 预算在执行下一个工具前检查：已产出的最终答案不会被预算拦截丢弃
            if limits.max_cost_usd and cost_usd > limits.max_cost_usd:
                trace.record("budget_exceeded", {
                    "step_id": context.step_id,
                    "cost_usd": round(cost_usd, 6),
                    "max_cost_usd": limits.max_cost_usd,
                })
                trace.record("step_finished", {"step_id": context.step_id})
                return AgentResult(
                    finish_reason="budget_exceeded",
                    error=f"cost {cost_usd:.4f} USD exceeded budget {limits.max_cost_usd} USD",
                    usage=total_usage, cost_usd=cost_usd,
                )
            call_id = f"call-{step}"
            trace.record("tool_call_started", {
                "tool_call_id": call_id, "tool": tool, "args": args,
            })
            result = await self.tools.execute(tool, args, allowed_tools)
            observation = _format_observation(tool, result)
            total_observation_chars += len(observation)
            if result.ok:
                trace.record("tool_call_finished", {
                    "tool_call_id": call_id,
                    "observation_chars": len(observation),
                    "total_observation_chars": total_observation_chars,
                    "observation": observation,
                })
                last_failed_signature = None
            else:
                trace.record("tool_call_error", {
                    "tool_call_id": call_id,
                    "status": result.status,
                    "error_code": result.error_code,
                })
                last_failed_signature = signature
            context.history.append({"role": "tool", "content": observation})
            trace.record("step_finished", {"step_id": context.step_id})
        return AgentResult(
            finish_reason="max_steps", error="max steps exhausted",
            usage=total_usage, cost_usd=cost_usd,
        )

    def _render(self, context: StepContext, allowed_tools: list[str]) -> str:
        labels = {"assistant": "【你】", "tool": "【工具】"}
        observations = "\n\n".join(
            f"{labels[m['role']]}{m['content']}" for m in context.history
        ) or "（暂无）"
        return self.prompt_template.format(
            instruction=context.instruction,
            tools_desc=self.tools.describe(allowed_tools),
            observations=observations,
        )


def _write_artifact(artifacts: Path, name: str, content: str) -> str:
    path = artifacts / name
    path.write_text(content, encoding="utf-8")
    return f"artifacts/{name}"


def _usage_trace_data(usage: TokenUsage | None) -> dict:
    if usage is None:
        return {}
    return {
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
        "total_tokens": usage.total_tokens,
    }


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
    if "action" not in value:
        # 宽容解析：模型直接输出答案 JSON（无 action 外壳）时按 answer 接受
        return {"kind": "answer", "answer": value}
    return None


def _format_observation(tool: str, result) -> str:
    # 截断由工具自身负责（如 read_file 的 max_chars），Runner 不做二次截断
    suffix = " [truncated]" if result.truncated else ""
    return f"[{tool}] status={result.status}{suffix}\n{result.observation}"
