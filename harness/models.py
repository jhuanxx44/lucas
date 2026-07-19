from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RunLimits:
    max_steps: int
    timeout_seconds: float
    max_cost_usd: float = 0.0


@dataclass
class AgentResult:
    answer: Any = None
    finish_reason: str = "completed"
    error: str = ""


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
