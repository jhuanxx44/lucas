from typing import Protocol

from utils.token_tracker import TokenUsage


class ModelAdapter(Protocol):
    async def complete(self, prompt: str) -> tuple[str, TokenUsage | None]: ...


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
