from dataclasses import dataclass, field


@dataclass
class StepContext:
    step_id: str
    instruction: str
    observations: list[str] = field(default_factory=list)
