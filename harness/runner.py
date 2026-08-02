import asyncio
import hashlib
import json
import time
from pathlib import Path
from typing import Callable

from harness.model_adapter import ModelAdapter
from harness.models import AgentResult, FunctionCall, ModelRequest, ModelTurn, RunLimits, StepContext
from harness.tools.base import ToolResult
from harness.tools.registry import ToolRuntime
from harness.trace import TraceRecorder
from utils.token_tracker import TokenUsage

MAX_OBSERVATION_CHARS = 10_000_000
MAX_MODEL_CORRECTIONS = 3
MAX_PARALLEL_TOOL_CALLS = 4  # 单轮并行工具调用上限；超出按协议错误纠正

# 阶段 1 Context 管理：触发阈值与轻量预估参数
CONTEXT_BUDGET_RATIO = 0.9          # 软线：输入 + 预留输出 > 窗口 * 0.9 时先压缩再提交
CONTEXT_HARD_RATIO = 0.95            # 硬线：软线压缩后预估仍 > 窗口 * 0.95 → 整轮 FIFO 兜底
RESERVED_OUTPUT_TOKENS = 16_384     # 预留输出空间，避免超窗请求在提交时报错
DEFAULT_TOKENS_PER_CHAR = 0.35      # 无校准数据时的默认 token/字符 系数（保守偏高）
CALIBRATION_WINDOW = 3              # 动态校准保留最近几轮
NON_COMPRESSIBLE_TOOLS = {"update_plan"}  # plan 是任务级状态，全程保留
PLACEHOLDER_PREFIX = "⚠️ [上下文压缩] "  # 已占位 output 的特征前缀，压缩时跳过
SUMMARY_MESSAGE_PREFIX = "⚠️ [上下文摘要] "  # 已由 LLM 摘要替换的历史消息前缀，压缩时跳过
SUMMARY_RESERVE_CHARS = 2_000               # 预留摘要输出本身占用的字符
SUMMARY_PROMPT_PATH = (
    Path(__file__).resolve().parent.parent / "prompts" / "harness" / "context-summary.md"
)


class _RunDeadlineExceeded(Exception):
    pass


class _NullTrace:
    def record(self, event: str, data: dict | None = None) -> None:
        return None


def _item_chars(item: dict) -> int:
    return len(json.dumps(item, ensure_ascii=False))


def _calibrated_ratio(calibration: list[tuple[int, int]]) -> float:
    """字符→token 动态系数：最近几轮真实 (新增字符, 新增 token) 的加权比值。"""
    pairs = calibration[-CALIBRATION_WINDOW:]
    total_chars = sum(chars for chars, _ in pairs)
    if total_chars <= 0:
        return DEFAULT_TOKENS_PER_CHAR
    return sum(tokens for _, tokens in pairs) / total_chars


def estimate_prompt_tokens(
    last_prompt_tokens: int | None,
    pending_chars: int,
    calibration: list[tuple[int, int]],
) -> int | None:
    """提交前轻量预估：上一轮真实 prompt_tokens + 本轮新增字符 × 动态系数。"""
    if last_prompt_tokens is None:
        return None
    return last_prompt_tokens + int(pending_chars * _calibrated_ratio(calibration))


def load_prompt_template(path: str | Path) -> str:
    """Load a prompt template and strip its llm-weight frontmatter."""
    text = Path(path).read_text(encoding="utf-8")
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[end + 4:].lstrip("\n")
    return text


class AgentRunner:
    """Native Responses loop; Lucas owns execution and explicit context items."""

    def __init__(
        self,
        model: ModelAdapter,
        tools: ToolRuntime,
        prompt_template: str,
        instructions: str = "",
        temperature: float = 0.0,
        context_window: int = 0,
        keep_recent_steps: int = 1,
        compression_level: int = 2,
        parallel_tool_calls: bool = True,
        summary_prompt: str | None = None,
    ):
        self.model = model
        self.tools = tools
        self.prompt_template = prompt_template
        self.instructions = instructions
        self.temperature = temperature
        # 0/None 表示关闭压缩：提交内容与 baseline 逐字节一致（简单任务零行为差异）
        self.context_window = context_window or 0
        self.keep_recent_steps = max(1, keep_recent_steps)
        # 压缩等级：1=纯机械（实验 baseline），2=链式（低损丢弃→LLM 摘要→FIFO 兜底，默认最高）
        self.compression_level = compression_level if compression_level in (1, 2) else 2
        self.parallel_tool_calls = parallel_tool_calls
        self.summary_prompt = summary_prompt or load_prompt_template(SUMMARY_PROMPT_PATH)

    def _reserved_output_tokens(self) -> int:
        """预留输出空间：常量与窗口 10% 取小，避免小窗口实验下过度保守。"""
        return min(RESERVED_OUTPUT_TOKENS, max(0, int(self.context_window * 0.1)))

    async def run(
        self,
        instruction: str,
        allowed_tools: list[str],
        limits: RunLimits,
        trace: TraceRecorder | None = None,
        on_event: Callable[[dict], None] | None = None,
        stream_answer: bool = False,
        on_trace_event: Callable[[dict], None] | None = None,
    ) -> AgentResult:
        initial_input = self.prompt_template.format(instruction=instruction)
        context = StepContext(
            step_id="",
            instruction=instruction,
            input_items=[{"role": "user", "content": initial_input}],
        )
        last_failed_signatures: dict[str, str] = {}  # tool -> 上次失败调用的参数签名
        seen_result_steps: dict[str, int] = {}
        stall_count = 0
        correction_count = 0
        total_observation_chars = 0
        total_usage: TokenUsage | None = None
        cost_usd = 0.0
        # ---- 阶段 1：token 预估与上下文压缩状态 ----
        last_prompt_tokens: int | None = None
        pending_items: list[dict] = []
        pending_added_chars = 0
        calibration: list[tuple[int, int]] = []
        item_steps: list[int] = [0]  # 与 context.input_items 平行：0=初始 user 消息
        call_info: dict[str, tuple[str, int]] = {}  # call_id -> (tool, step)
        run_started = time.monotonic()
        deadline = (
            run_started + limits.timeout_seconds
            if limits.timeout_seconds and limits.timeout_seconds > 0 else None
        )
        artifacts: Path | None = None
        if trace is not None:
            artifacts = trace.path.parent / "artifacts"
            artifacts.mkdir(exist_ok=True)
        else:
            trace = _NullTrace()

        def append_items(items: list[dict], step_id: int) -> None:
            nonlocal pending_added_chars
            for item in items:
                context.input_items.append(item)
                item_steps.append(step_id)
                pending_items.append(item)
                pending_added_chars += _item_chars(item)

        def append_model_items(turn: ModelTurn, step_id: int) -> None:
            """把本轮模型返回的 items（message/function_call/reasoning）追加一次。"""
            append_items(turn.response_items, step_id)

        def append_tool_output(call_id: str, output: str, step_id: int, tool: str) -> None:
            """追加单个工具结果；并行多调用时每个 call_id 各追加一次。"""
            append_items([{"type": "function_call_output", "call_id": call_id, "output": output}], step_id)
            call_info[call_id] = (tool, step_id)

        async def await_before_deadline(awaitable):
            if deadline is None:
                return await awaitable
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                if hasattr(awaitable, "close"):
                    awaitable.close()
                raise _RunDeadlineExceeded
            try:
                return await asyncio.wait_for(awaitable, timeout=remaining)
            except TimeoutError as error:
                if time.monotonic() >= deadline:
                    raise _RunDeadlineExceeded from error
                raise

        def _merge_usage(turn: ModelTurn) -> None:
            """摘要调用同样计入全 run 的 usage 与成本。"""
            nonlocal total_usage, cost_usd
            if turn.usage is None:
                return
            total_usage = turn.usage if total_usage is None else total_usage.merge(turn.usage)
            cost_usd = total_usage.total_cost

        def _render_step_text(st: int, item: dict) -> str:
            kind = item.get("type")
            if kind == "function_call":
                return f"第 {st} 步 工具调用 {item.get('name')}：{item.get('arguments', '')}"
            if kind == "function_call_output":
                return f"第 {st} 步 工具结果：{item.get('output', '')}"
            content = item.get("content", "")
            if not isinstance(content, str):
                content = json.dumps(content, ensure_ascii=False)
            return f"第 {st} 步：{content}"

        async def _summarize_steps(steps_text: str) -> ModelTurn | None:
            """一次轻量模型调用（llm-weight: light 模板）生成交接摘要；失败返回 None。"""
            request = ModelRequest(
                instructions="",
                input_items=[{
                    "role": "user",
                    "content": f"{self.summary_prompt}\n\n{steps_text}",
                }],
                tools=[],
                temperature=0.0,
            )
            turn = await await_before_deadline(self.model.complete(request))
            _merge_usage(turn)
            if turn.protocol_error or not turn.output_text.strip():
                return None
            return turn

        async def compress_context(trigger_estimate: int) -> dict | None:
            """三级链式上下文压缩（compression_level=2 默认）：
            1) 低价值丢弃：更早步骤的 reasoning 与中间 assistant 叙述（成本 0）；
            2) LLM 摘要：最早可压缩步骤合并成一条交接摘要（成本 1 次调用），取代占位挖空；
               摘要失败时降级为占位挖空（degraded），仍释放部分 token；
            3) 有损机械兜底：软线逐条丢 assistant 消息，硬线（0.95）整轮 FIFO。
            compression_level=1 只走 1(仅 reasoning)+占位挖空+3，与旧行为一致。
            返回压缩摘要（mode 为链式各级 '+' 连接）或 None（无可压缩项）。"""
            nonlocal pending_added_chars
            ratio = _calibrated_ratio(calibration)
            oldest_kept_step = step - self.keep_recent_steps
            plan_steps = {
                st for (tool, st) in call_info.values() if tool in NON_COMPRESSIBLE_TOOLS
            }
            chars_delta = 0
            dropped_steps: set[int] = set()
            placeholder_count = 0
            mode_parts: list[str] = []
            summary_covered: list[int] = []
            degraded = False

            def estimate_with(total_delta: int) -> int:
                return estimate_prompt_tokens(
                    last_prompt_tokens, pending_added_chars + total_delta, calibration
                ) or trigger_estimate

            def over_soft_budget() -> bool:
                return (
                    estimate_with(chars_delta) + self._reserved_output_tokens()
                    > self.context_window * CONTEXT_BUDGET_RATIO
                )

            # ---- 链式第 1 级：低价值丢弃（reasoning；链式模式含中间 assistant 叙述）----
            kept: list[tuple[dict, int]] = []
            for item, st in zip(context.input_items, item_steps):
                if st > 0 and st < oldest_kept_step:
                    kind = item.get("type")
                    if kind == "reasoning" or (self.compression_level >= 2 and kind == "message"):
                        chars_delta -= _item_chars(item)
                        dropped_steps.add(st)
                        continue
                kept.append((item, st))
            if chars_delta != 0 or dropped_steps:
                mode_parts.append("drop")

            if self.compression_level >= 2:
                # ---- 链式第 2 级：LLM 摘要（取代占位挖空）----
                if over_soft_budget():
                    # 按步聚合更早的可压缩内容；跳过 plan 步骤、已占位/已摘要内容
                    step_items: dict[int, list[tuple[int, dict]]] = {}
                    for idx, (item, st) in enumerate(kept):
                        if st <= 0 or st >= oldest_kept_step or st in plan_steps:
                            continue
                        if item.get("type") == "function_call_output":
                            output = item.get("output", "")
                            if output.startswith(PLACEHOLDER_PREFIX):
                                continue
                            tool, _ = call_info.get(item.get("call_id"), ("?", st))
                            if tool in NON_COMPRESSIBLE_TOOLS:
                                continue
                        if (
                            item.get("role") == "user"
                            and str(item.get("content", "")).startswith(SUMMARY_MESSAGE_PREFIX)
                        ):
                            continue
                        step_items.setdefault(st, []).append((idx, item))

                    excess = (
                        estimate_with(chars_delta) + self._reserved_output_tokens()
                        - self.context_window * CONTEXT_BUDGET_RATIO
                    )
                    need_chars = int(excess / ratio) + SUMMARY_RESERVE_CHARS
                    # 摘要请求本身必须放得进窗口：输入上限按窗口 80%（token）折算
                    max_input_chars = max(2_000, int(self.context_window * 0.8 / ratio))
                    cover_steps: list[int] = []
                    cover_idxs: list[int] = []
                    input_parts: list[str] = []
                    cover_chars = 0
                    for st, items in step_items.items():
                        step_chars = sum(_item_chars(it) for _, it in items)
                        if cover_chars + step_chars > max_input_chars:
                            continue  # 单步过大：跳过，留给第 3 级兜底
                        cover_steps.append(st)
                        cover_idxs.extend(i for i, _ in items)
                        cover_chars += step_chars
                        input_parts.extend(_render_step_text(st, it) for _, it in items)
                        if cover_chars >= need_chars:
                            break

                    if cover_steps:
                        try:
                            turn = await _summarize_steps("\n\n".join(input_parts))
                        except _RunDeadlineExceeded:
                            turn = None  # 摘要超时：降级为机械，避免拖垮整个 run
                        except Exception:
                            turn = None
                        if turn is not None:
                            summary_text = turn.output_text.strip()
                            summary_item = {
                                "role": "user",
                                "content": (
                                    f"{SUMMARY_MESSAGE_PREFIX}覆盖第 {cover_steps[0]}–{cover_steps[-1]} 步；"
                                    f"这些步骤的历史已由摘要替换。\n\n{summary_text}"
                                ),
                            }
                            # 移除被覆盖 items，在最早覆盖位置插入摘要消息（保持时间顺序）
                            removed = set(cover_idxs)
                            new_kept: list[tuple[dict, int]] = []
                            inserted = False
                            for idx, pair in enumerate(kept):
                                if idx in removed:
                                    continue
                                if not inserted and idx > min(cover_idxs):
                                    new_kept.append((summary_item, cover_steps[0]))
                                    inserted = True
                                new_kept.append(pair)
                            if not inserted:
                                new_kept.append((summary_item, cover_steps[0]))
                            kept = new_kept
                            chars_delta -= cover_chars
                            chars_delta += _item_chars(summary_item)
                            dropped_steps.update(cover_steps)
                            summary_covered = cover_steps
                            mode_parts.append("summarize")
                            trace.record("context_summarized", {
                                "step_id": context.step_id,
                                "covered_steps": cover_steps,
                                "covered_chars": cover_chars,
                                "summary_chars": len(summary_text),
                            })
                        else:
                            # 摘要失败：降级为占位挖空（与 level=1 一致），仍释放部分 token
                            degraded = True
                            mode_parts.append("degraded")
                            for idx in sorted(cover_idxs):
                                item, st = kept[idx]
                                if item.get("type") != "function_call_output":
                                    continue
                                if item.get("output", "").startswith(PLACEHOLDER_PREFIX):
                                    continue
                                tool, _ = call_info.get(item.get("call_id"), ("?", st))
                                if tool in NON_COMPRESSIBLE_TOOLS:
                                    continue
                                old_chars = _item_chars(item)
                                tokens = max(1, int(old_chars * ratio))
                                kept[idx] = ({
                                    **item,
                                    "output": (
                                        f"{PLACEHOLDER_PREFIX}第 {st} 步 {tool} 工具结果因上下文压缩被丢弃"
                                        f"（约 {tokens} token）；该步骤已执行，回答时请勿假设其结果内容。"
                                    ),
                                }, st)
                                chars_delta += _item_chars(kept[idx][0]) - old_chars
                                placeholder_count += 1
                                dropped_steps.add(st)
            else:
                # ---- 纯机械（level=1）：占位挖空更早 tool output ----
                new_kept: list[tuple[dict, int]] = []
                for item, st in kept:
                    if (
                        st > 0 and st < oldest_kept_step
                        and item.get("type") == "function_call_output"
                    ):
                        tool, _ = call_info.get(item.get("call_id"), ("?", st))
                        if tool in NON_COMPRESSIBLE_TOOLS or item.get("output", "").startswith(PLACEHOLDER_PREFIX):
                            new_kept.append((item, st))
                            continue
                        old_chars = _item_chars(item)
                        tokens = max(1, int(old_chars * ratio))
                        placeholder = {
                            **item,
                            "output": (
                                f"{PLACEHOLDER_PREFIX}第 {st} 步 {tool} 工具结果因上下文压缩被丢弃"
                                f"（约 {tokens} token）；该步骤已执行，回答时请勿假设其结果内容。"
                            ),
                        }
                        chars_delta += _item_chars(placeholder) - old_chars
                        new_kept.append((placeholder, st))
                        placeholder_count += 1
                        dropped_steps.add(st)
                    else:
                        new_kept.append((item, st))
                kept = new_kept

            # ---- 兜底 1：软线仍超 → 从最早丢 assistant 消息 / reasoning ----
            pending_remaining = len(pending_items)
            index = 0
            while (
                index < len(kept)
                and over_soft_budget()
            ):
                item, st = kept[index]
                if st > 0 and item.get("type") in ("message", "reasoning"):
                    chars = _item_chars(item)
                    if index >= len(kept) - pending_remaining:
                        pending_remaining -= 1
                    else:
                        chars_delta -= chars
                    dropped_steps.add(st)
                    kept.pop(index)
                else:
                    index += 1

            # ---- 兜底 2（链式第 3 级）：硬线（0.95）→ 从最早 step 整轮 FIFO（成对丢，
            # 结构完整），直到 ≤ 0.95×窗口或只剩 step 0；pending 项删后由末尾重算。----
            fifo_ran = False
            if estimate_with(chars_delta) > self.context_window * CONTEXT_HARD_RATIO:
                while kept and estimate_with(chars_delta) > self.context_window * CONTEXT_HARD_RATIO:
                    boundary = len(kept) - pending_remaining
                    target = next(
                        (st for idx, (_, st) in enumerate(kept[:boundary]) if st > 0),
                        None,
                    )
                    if target is None:
                        break  # 只剩 step 0，无可再删
                    removed_chars = 0
                    fifo_kept: list[tuple[dict, int]] = []
                    for idx, (item, st) in enumerate(kept):
                        if st == target:
                            if idx >= len(kept) - pending_remaining:
                                pending_remaining -= 1
                            else:
                                removed_chars += _item_chars(item)
                        else:
                            fifo_kept.append((item, st))
                    kept = fifo_kept
                    chars_delta -= removed_chars
                    dropped_steps.add(target)
                    fifo_ran = True
            if fifo_ran:
                mode_parts.append("fifo")

            if placeholder_count == 0 and chars_delta == 0 and not dropped_steps:
                return None
            kept_items = [item for item, _ in kept]
            kept_steps = [st for _, st in kept]
            context.input_items[:] = kept_items
            item_steps[:] = kept_steps
            pending_items[:] = kept_items[len(kept_items) - pending_remaining:]
            pending_added_chars = sum(_item_chars(item) for item in pending_items)
            after_estimate = estimate_with(chars_delta)
            return {
                "trigger_estimate": trigger_estimate,
                "after_estimate": after_estimate,
                "freed_tokens": max(0, trigger_estimate - after_estimate),
                "dropped_steps": sorted(dropped_steps),
                "placeholder_count": placeholder_count,
                "summary_covered": summary_covered,
                "degraded": degraded,
                "level": self.compression_level,
                "chain": mode_parts,
                "mode": "+".join(mode_parts) or "soft",
            }

        def timeout_result(phase: str) -> AgentResult:
            elapsed = time.monotonic() - run_started
            trace.record("timeout", {
                "step_id": context.step_id,
                "phase": phase,
                "elapsed_seconds": round(elapsed, 3),
                "timeout_seconds": limits.timeout_seconds,
            })
            return AgentResult(
                finish_reason="timeout",
                error=f"elapsed {elapsed:.1f}s exceeded timeout {limits.timeout_seconds}s",
                usage=total_usage,
                cost_usd=cost_usd,
            )

        step = 0
        while limits.max_steps <= 0 or step < limits.max_steps:
            step += 1
            if deadline is not None and time.monotonic() >= deadline:
                return timeout_result("between_steps")
            context.step_id = f"step-{step}"
            trace.record("step_started", {"step_id": context.step_id})
            compressed_this_round = False

            if self.context_window > 0:
                if last_prompt_tokens is None:
                    # 开始时超线（初始预估）：无上一轮真实 usage，用初始 items 字符 × 默认系数
                    initial_chars = sum(_item_chars(item) for item in context.input_items)
                    trigger_estimate = int(initial_chars * DEFAULT_TOKENS_PER_CHAR)
                    if trigger_estimate + self._reserved_output_tokens() > self.context_window * CONTEXT_BUDGET_RATIO:
                        # 初始只有 step 0，无可压缩；记录触发。超硬线则拦截：不提交必败请求
                        trace.record("context_compressed", {
                            "step_id": context.step_id,
                            "trigger_estimate_tokens": trigger_estimate,
                            "estimate_after_tokens": trigger_estimate,
                            "freed_tokens": 0,
                            "dropped_steps": [],
                            "placeholder_count": 0,
                            "keep_recent_steps": self.keep_recent_steps,
                            "compression_level": self.compression_level,
                            "mode": "soft",
                        })
                        if on_event is not None:
                            on_event({
                                "kind": "context_compressed",
                                "step": step,
                                "before_estimated_tokens": trigger_estimate,
                                "after_estimated_tokens": trigger_estimate,
                                "freed_tokens": 0,
                                "dropped_steps": [],
                                "level": self.compression_level,
                                "mode": "soft",
                            })
                        if trigger_estimate > self.context_window * CONTEXT_HARD_RATIO:
                            trace.record("context_limit_exceeded", {
                                "step_id": context.step_id,
                                "estimated_tokens": trigger_estimate,
                                "hard_limit_tokens": int(self.context_window * CONTEXT_HARD_RATIO),
                            })
                            return AgentResult(
                                finish_reason="context_limit_exceeded",
                                error=(
                                    f"initial context ~{trigger_estimate} tokens exceeds "
                                    f"hard limit {int(self.context_window * CONTEXT_HARD_RATIO)}"
                                ),
                                usage=total_usage,
                                cost_usd=cost_usd,
                            )
                else:
                    trigger_estimate = estimate_prompt_tokens(
                        last_prompt_tokens, pending_added_chars, calibration
                    )
                    if (
                        trigger_estimate is not None
                        and trigger_estimate + self._reserved_output_tokens() > self.context_window * CONTEXT_BUDGET_RATIO
                    ):
                        compressed = await compress_context(trigger_estimate)
                        if compressed is not None:
                            compressed_this_round = True
                            trace.record("context_compressed", {
                                "step_id": context.step_id,
                                "trigger_estimate_tokens": trigger_estimate,
                                "estimate_after_tokens": compressed["after_estimate"],
                                "freed_tokens": compressed["freed_tokens"],
                                "dropped_steps": compressed["dropped_steps"],
                                "placeholder_count": compressed["placeholder_count"],
                                "summary_covered": compressed["summary_covered"],
                                "degraded": compressed["degraded"],
                                "keep_recent_steps": self.keep_recent_steps,
                                "compression_level": compressed["level"],
                                "chain": compressed["chain"],
                                "mode": compressed["mode"],
                            })
                            if on_event is not None:
                                on_event({
                                    "kind": "context_compressed",
                                    "step": step,
                                    "before_estimated_tokens": trigger_estimate,
                                    "after_estimated_tokens": compressed["after_estimate"],
                                    "freed_tokens": compressed["freed_tokens"],
                                    "dropped_steps": compressed["dropped_steps"],
                                    "level": compressed["level"],
                                    "chain": compressed["chain"],
                                    "degraded": compressed["degraded"],
                                    "mode": compressed["mode"],
                                })

            request = ModelRequest(
                instructions=self.instructions,
                input_items=list(context.input_items),
                tools=self.tools.available(allowed_tools),
                temperature=self.temperature,
                parallel_tool_calls=self.parallel_tool_calls,
            )
            submitted_pending_chars = pending_added_chars
            pending_items.clear()
            pending_added_chars = 0
            serialized_input = json.dumps(request.input_items, ensure_ascii=False, indent=2)
            input_ref = (
                _write_artifact(artifacts, f"input-{context.step_id}.json", serialized_input)
                if artifacts is not None else None
            )
            trace.record("model_input_prepared", {
                "step_id": context.step_id,
                "input_items": len(request.input_items),
                "input_chars": len(serialized_input),
                "artifact": input_ref,
            })
            if on_trace_event is not None:
                on_trace_event({"kind": "model_input", "step": step, "input": request.input_items})
            trace.record("model_call_started", {
                "step_id": context.step_id,
                "model_call_id": f"model-{step}",
            })
            trace.record("response_started", {"step_id": context.step_id})

            use_stream = stream_answer and on_event is not None and hasattr(self.model, "complete_stream")
            # 已实时推送的 answer 字符数；流式中途失败回退 complete() 时仍保留，
            # 供下游按最终答案补尾防缺字。
            stream_state = {"streamed": 0}
            started = time.monotonic()
            try:
                if use_stream:
                    try:
                        turn = await await_before_deadline(
                            self._complete_streaming(request, step, on_event, stream_state)
                        )
                    except _RunDeadlineExceeded:
                        return timeout_result("model_call")
                    except Exception as error:
                        trace.record("answer_stream_fallback", {
                            "step_id": context.step_id,
                            "error": str(error)[:200],
                        })
                        turn = await await_before_deadline(self.model.complete(request))
                else:
                    turn = await await_before_deadline(self.model.complete(request))
            except _RunDeadlineExceeded:
                return timeout_result("model_call")

            if turn.function_calls and stream_state["streamed"] > 0 and on_event is not None:
                # 工具轮（含被拒绝的混合轮）流出的 output_text 只是中间叙述，
                # 不是最终答案，通知下游清掉已展示的临时文本
                on_event({"kind": "answer_discard"})

            duration_ms = (time.monotonic() - started) * 1000
            if turn.usage is not None:
                prev_prompt_tokens = last_prompt_tokens
                last_prompt_tokens = turn.usage.prompt_tokens
                if (
                    prev_prompt_tokens is not None
                    and submitted_pending_chars > 0
                    and not compressed_this_round
                ):
                    # 压缩轮 Δprompt 混入了老 items 被挖空的净变化，不参与系数校准
                    added_tokens = turn.usage.prompt_tokens - prev_prompt_tokens
                    if added_tokens > 0:
                        calibration.append((submitted_pending_chars, added_tokens))
                        del calibration[:-CALIBRATION_WINDOW]
                total_usage = turn.usage if total_usage is None else total_usage.merge(turn.usage)
                if on_event is not None:
                    on_event({
                        "kind": "usage",
                        "step": step,
                        "prompt_tokens": turn.usage.prompt_tokens,
                        "total_tokens": turn.usage.total_tokens,
                    })
            cost_usd = total_usage.total_cost if total_usage is not None else 0.0
            output_json = json.dumps(turn.response_items, ensure_ascii=False, indent=2)
            output_ref = (
                _write_artifact(artifacts, f"output-{context.step_id}.json", output_json)
                if artifacts is not None else None
            )
            trace.record("model_call_finished", {
                "step_id": context.step_id,
                "model_call_id": f"model-{step}",
                "duration_ms": round(duration_ms, 1),
                "output_chars": len(turn.output_text),
                "output_items": len(turn.response_items),
                "response_id": turn.response_id,
                "artifact": output_ref,
                **_usage_trace_data(turn.usage),
            })
            trace.record("response_completed", {
                "step_id": context.step_id,
                "response_id": turn.response_id,
                "output_items": len(turn.response_items),
            })
            for retry in turn.provider_retries:
                trace.record("provider_retry", {
                    "step_id": context.step_id,
                    **retry,
                })
            if turn.reasoning:
                trace.record("model_reasoning", {
                    "step_id": context.step_id,
                    "text": turn.reasoning,
                })
            if turn.commentary:
                trace.record("model_commentary", {
                    "step_id": context.step_id,
                    "text": turn.commentary,
                })
            if on_trace_event is not None:
                on_trace_event({
                    "kind": "model_output",
                    "step": step,
                    "response_id": turn.response_id,
                    "output_text": turn.output_text,
                    "items": turn.response_items,
                })

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
                    usage=total_usage,
                    cost_usd=cost_usd,
                )

            decision_error = _decision_error(turn)
            if decision_error:
                correction_count += 1
                trace.record("model_correction", {
                    "step_id": context.step_id,
                    "reason": decision_error,
                    "correction_count": correction_count,
                })
                trace.record("step_finished", {"step_id": context.step_id})
                if correction_count > MAX_MODEL_CORRECTIONS:
                    return AgentResult(
                        finish_reason="protocol_error",
                        error=f"model protocol correction exhausted: {decision_error}",
                        usage=total_usage,
                        cost_usd=cost_usd,
                    )
                append_items([{
                    "role": "user",
                    "content": (
                        f"上一响应不符合工具协议：{decision_error}。"
                        "请重新作出一次决策：需要工具时只返回 function_call item"
                        f"（单轮最多 {MAX_PARALLEL_TOOL_CALLS} 个，仅限互不依赖的调用）；"
                        "任务完成时只返回最终答案。"
                    ),
                }], step)
                continue

            correction_count = 0
            if not turn.function_calls:
                answer_text = turn.output_text
                trace.record("assistant_answer", {
                    "step_id": context.step_id,
                    "answer_preview": answer_text[:500],
                })
                trace.record("step_finished", {"step_id": context.step_id})
                if on_event is not None:
                    on_event({
                        "kind": "answer",
                        "step": step,
                        "answer": answer_text,
                        "streamed_chars": stream_state["streamed"],
                    })
                return AgentResult(
                    answer=answer_text,
                    finish_reason="completed",
                    usage=total_usage,
                    cost_usd=cost_usd,
                )

            # 并行工具调用：模型 items 只追加一次；同一批调用先广播全部 tool_start，
            # 再并发执行，最后按原顺序回传各 call 的 output。
            # Responses API 要求同一批 function_call 的 function_call_output 一起提交，
            # 因此全部调用执行完、全部 output 追加完才进入下一轮。
            append_model_items(turn, step)
            pending: list[tuple[FunctionCall, tuple[str, str]]] = []
            for call in turn.function_calls:
                tool, args = call.name, call.arguments
                trace.record("function_call_received", {
                    "step_id": context.step_id,
                    "tool_call_id": call.call_id,
                    "tool": tool,
                    "args": args,
                    "summary": call.summary,
                })
                if on_event is not None:
                    on_event({
                        "kind": "summary", "step": step, "tool": tool,
                        "call_id": call.call_id, "text": call.summary,
                    })

                signature = (tool, json.dumps(args, sort_keys=True, ensure_ascii=False))
                if last_failed_signatures.get(tool) == signature:
                    observation = (
                        f"警告：{tool} 连续两次以相同参数调用失败。"
                        "请换用其他工具、换一组参数，或基于已有信息作答。"
                    )
                    trace.record("tool_call_repeated_failure", {
                        "step_id": context.step_id,
                        "tool": tool,
                        "args": args,
                    })
                    append_tool_output(call.call_id, observation, step, tool)
                    trace.record("function_call_output", {
                        "tool_call_id": call.call_id,
                        "observation": observation,
                    })
                    if on_event is not None:
                        on_event({
                            "kind": "tool_step",
                            "step": step,
                            "tool": tool,
                            "call_id": call.call_id,
                            "args": args,
                            "ok": False,
                            "observation": observation,
                        })
                    continue

                pending.append((call, signature))
                trace.record("tool_call_started", {
                    "tool_call_id": call.call_id,
                    "tool": tool,
                    "args": args,
                })
                if on_event is not None:
                    on_event({
                        "kind": "tool_start",
                        "step": step,
                        "tool": tool,
                        "call_id": call.call_id,
                        "args": args,
                    })

            # 并发执行全部待执行调用；结果按原顺序处理，观测预算/停滞检测保持确定性
            outcomes = await asyncio.gather(
                *(
                    await_before_deadline(self.tools.execute(call.name, call.arguments, allowed_tools))
                    for call, _ in pending
                ),
                return_exceptions=True,
            )
            for (call, (tool, signature)), outcome in zip(pending, outcomes):
                if isinstance(outcome, asyncio.CancelledError):
                    raise outcome
                if isinstance(outcome, _RunDeadlineExceeded):
                    return timeout_result("tool_call")
                if isinstance(outcome, BaseException):
                    result = ToolResult(
                        status="error",
                        error_code="handler_exception",
                        observation=f"{type(outcome).__name__}: {outcome}",
                    )
                else:
                    result = outcome
                full_observation = _format_observation(tool, result)
                remaining_observation_chars = max(0, MAX_OBSERVATION_CHARS - total_observation_chars)
                observation, was_truncated = _truncate_observation(
                    full_observation,
                    min(MAX_OBSERVATION_CHARS, remaining_observation_chars),
                )
                if was_truncated:
                    result.truncated = True
                total_observation_chars += len(observation)

                if result.ok:
                    trace.record("tool_call_finished", {
                        "tool_call_id": call.call_id,
                        "observation_chars": len(observation),
                        "total_observation_chars": total_observation_chars,
                        "observation": observation,
                        "truncated": result.truncated,
                    })
                    last_failed_signatures.pop(tool, None)
                    result_hash = hashlib.sha256(observation.encode("utf-8")).hexdigest()
                    first_step = seen_result_steps.get(result_hash)
                    # 同一并行轮内两个调用返回相同结果不算停滞（模型还没机会根据结果调整）
                    if first_step is not None and first_step != step:
                        stall_count += 1
                        function_output = _stall_note(tool, first_step)
                        trace.record("no_progress_detected", {
                            "step_id": context.step_id,
                            "tool": tool,
                            "repeated_from_step": first_step,
                            "stall_count": stall_count,
                        })
                    else:
                        seen_result_steps[result_hash] = step
                        function_output = observation
                else:
                    trace.record("tool_call_error", {
                        "tool_call_id": call.call_id,
                        "status": result.status,
                        "error_code": result.error_code,
                    })
                    last_failed_signatures[tool] = (tool, signature)
                    function_output = observation

                append_tool_output(call.call_id, function_output, step, tool)
                trace.record("function_call_output", {
                    "tool_call_id": call.call_id,
                    "observation": function_output,
                })
                if on_event is not None:
                    on_event({
                        "kind": "tool_step",
                        "step": step,
                        "tool": tool,
                        "call_id": call.call_id,
                        # 每个调用必须携带自己发出的参数：不能用第一个循环残留的
                        # 变量 args（整批共享最后一个 call 的参数）；signature 是
                        # 发起调用时的参数快照，与模型发出的参数完全一致
                        "args": json.loads(signature),
                        "ok": result.ok,
                        "observation": observation,
                    })
            trace.record("step_finished", {"step_id": context.step_id})

        return AgentResult(
            finish_reason="max_steps",
            error="max steps exhausted",
            usage=total_usage,
            cost_usd=cost_usd,
        )

    async def _complete_streaming(
        self,
        request: ModelRequest,
        step: int,
        on_event: Callable[[dict], None],
        stream_state: dict,
    ) -> ModelTurn:
        """实时转发答案 delta；completed turn 提供最终答案与 usage。

        DeepSeek 工具轮也可能产出 output_text.delta（中间叙述，item 顺序
        不可靠），因此文本一律实时转发，由本 runner 在 turn 完成且确认
        是工具轮后发出 answer_discard 丢弃。
        """
        completed_turn: ModelTurn | None = None
        async for event in self.model.complete_stream(request):
            if event.kind == "reasoning_delta":
                if event.text:
                    on_event({"kind": "thought", "step": step, "text": event.text})
            elif event.kind == "output_text_delta":
                stream_state["streamed"] += len(event.text)
                on_event({"kind": "answer_chunk", "step": step, "text": event.text})
            elif event.kind == "completed":
                completed_turn = event.turn
        if completed_turn is None:
            raise RuntimeError("model stream did not produce a completed turn")
        return completed_turn


def _decision_error(turn: ModelTurn) -> str:
    if turn.protocol_error:
        return turn.protocol_error
    if len(turn.function_calls) > MAX_PARALLEL_TOOL_CALLS:
        return f"response returned more than {MAX_PARALLEL_TOOL_CALLS} function calls"
    if turn.function_calls and turn.output_text.strip():
        return "response mixed a function call with final output text"
    if not turn.function_calls and not turn.output_text.strip():
        return "response contained neither a function call nor final output text"
    return ""


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
        "thinking_tokens": usage.thinking_tokens,
        "total_tokens": usage.total_tokens,
    }


def _format_observation(tool: str, result) -> str:
    suffix = " [truncated]" if result.truncated else ""
    return f"[{tool}] status={result.status}{suffix}\n{result.observation}"


def _stall_note(tool: str, first_step: int) -> str:
    return (
        f"⚠️ 停滞：{tool} 返回结果与第 {first_step} 步完全相同，"
        "继续当前方式不会获得新信息。\n"
        "先盘点已经掌握的内容，想想还缺什么——然后换个思路再试。"
    )


def _truncate_observation(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    marker = "\n…[tool observation truncated]"
    if limit <= 0:
        return "", True
    if limit <= len(marker):
        return marker[:limit], True
    return text[:limit - len(marker)] + marker, True
