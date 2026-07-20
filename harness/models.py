from dataclasses import dataclass, field
from typing import Any

from utils.token_tracker import TokenUsage


@dataclass(frozen=True)
class RunLimits:
    max_steps: int
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


@dataclass
class StepContext:
    step_id: str
    instruction: str
    # 全量消息回放：{"role": "assistant", "content": 模型原始输出}
    #             {"role": "tool", "content": observation 或反馈}
    history: list[dict] = field(default_factory=list)
