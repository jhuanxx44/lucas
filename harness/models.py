from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from utils.token_tracker import TokenUsage

if TYPE_CHECKING:
    from harness.tools.base import ToolSpec


@dataclass(frozen=True)
class RunLimits:
    max_steps: int
    # 0 或 <=0 表示不限制步数；>0 表示步数上限
    # 总 run 硬 deadline；None 或 <=0 表示不限制（与 max_cost_usd 约定一致）
    timeout_seconds: float
    # 0 或 None 表示不限制成本（evals 任务里 max_cost_usd: 0 即"未设置"）
    max_cost_usd: float = 0.0


@dataclass
class AgentResult:
    answer: Any = None
    finish_reason: str = "completed"
    error: str = ""
    # 全 run 累计的 token 用量；模型不返回 usage 时为 None
    usage: TokenUsage | None = None
    # 按 token_tracker 价格表估算的累计成本（无 usage 时为 0.0）
    cost_usd: float = 0.0


@dataclass(frozen=True)
class TraceEvent:
    sequence: int
    run_id: str
    timestamp: str
    event: str
    data: dict


@dataclass(frozen=True)
class FunctionCall:
    """Provider-neutral native function call returned by a model."""

    call_id: str
    name: str
    arguments: dict
    summary: str
    raw_arguments: str = ""


@dataclass(frozen=True)
class ModelRequest:
    """One explicit Responses request; Lucas owns every submitted input item."""

    instructions: str
    input_items: list[dict[str, Any]]
    tools: list[ToolSpec]
    temperature: float = 0.0
    # 是否允许模型单轮返回多个互不依赖的 function_call（并行工具调用）
    parallel_tool_calls: bool = True


@dataclass
class ModelTurn:
    """Normalized result of one Responses call."""

    output_text: str = ""
    commentary: str = ""
    function_calls: list[FunctionCall] = field(default_factory=list)
    reasoning: str = ""
    usage: TokenUsage | None = None
    response_id: str = ""
    response_items: list[dict[str, Any]] = field(default_factory=list)
    provider_retries: list[dict[str, Any]] = field(default_factory=list)
    protocol_error: str = ""


@dataclass
class ModelEvent:
    """Normalized streaming event; completed carries the authoritative turn."""

    kind: str
    text: str = ""
    turn: ModelTurn | None = None


@dataclass
class StepContext:
    step_id: str
    instruction: str
    # Responses 显式输入：user message、上一轮完整 response.output、
    # function_call_output 等。Lucas 持有全部上下文，不依赖 previous_response_id。
    input_items: list[dict[str, Any]] = field(default_factory=list)
