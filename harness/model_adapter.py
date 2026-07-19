from typing import AsyncIterator, Protocol

from utils.token_tracker import TokenUsage


class ModelAdapter(Protocol):
    async def complete(self, prompt: str) -> tuple[str, TokenUsage | None]: ...

    # 可选方法：实现后 Runner（stream_answer=True 且带 on_event）走流式路径。
    # 仅逐段产出原始文本 chunk；流式无 usage 时由 Runner 记 None。
    async def complete_stream(self, prompt: str) -> AsyncIterator[str]: ...


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

    async def complete_stream(self, prompt: str) -> AsyncIterator[str]:
        # 保持 json mime：流式同样输出完整 JSON（reply 提取由 AnswerStreamParser 负责）
        async for chunk in self.client.chat_stream(
            prompt,
            response_mime_type="application/json",
            temperature=self.temperature,
        ):
            yield chunk
