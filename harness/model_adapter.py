from typing import AsyncIterator, Protocol

from utils.token_tracker import TokenUsage


class ModelAdapter(Protocol):
    async def complete(self, prompt: str) -> tuple[str, TokenUsage | None]: ...

    # 可选方法：实现后 Runner（stream_answer=True 且带 on_event）走流式路径。
    # 逐段产出 (kind, text)：kind 为 "reasoning"（过程思考）或 "content"（答案）；
    # 流式无 usage 时由 Runner 记 None。
    async def complete_stream(self, prompt: str) -> AsyncIterator[tuple[str, str]]: ...


class LLMClientAdapter:
    """包装产品侧 LLMClient 为 ModelAdapter 协议"""

    def __init__(self, client, temperature: float = 0.0):
        self.client = client
        self.temperature = temperature

    async def complete(self, prompt: str) -> tuple[str, TokenUsage | None]:
        return await self.client.chat(
            prompt,
            response_mime_type="application/json",
            temperature=self.temperature,
        )

    async def complete_stream(self, prompt: str) -> AsyncIterator[tuple[str, str]]:
        # 保持 json mime：content 段仍是完整 JSON（reply 提取由 AnswerStreamParser 负责）；
        # reasoning 段是模型原生独立思考通道，透传给上层展示为过程 thought。
        async for kind, text in self.client.chat_stream(
            prompt,
            response_mime_type="application/json",
            temperature=self.temperature,
        ):
            yield kind, text
