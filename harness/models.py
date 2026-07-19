from dataclasses import dataclass, field


@dataclass
class StepContext:
    step_id: str
    instruction: str
    # 全量消息回放：{"role": "assistant", "content": 模型原始输出}
    #             {"role": "tool", "content": observation 或反馈}
    history: list[dict] = field(default_factory=list)
