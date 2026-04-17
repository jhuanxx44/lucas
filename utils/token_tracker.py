"""Token 统计模块（精简版，从 pptgenaiserver 移植）"""
from dataclasses import dataclass
from typing import Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    thinking_tokens: int = 0
    total_tokens: int = 0
    model: str = ""
    latency_ms: float = 0.0

    @property
    def total_cost(self) -> float:
        input_cost = (self.prompt_tokens / 1_000_000) * 2.0
        output_cost = (self.completion_tokens / 1_000_000) * 12.0
        thinking_cost = (self.thinking_tokens / 1_000_000) * 12.0
        return input_cost + output_cost + thinking_cost

    def merge(self, other: 'TokenUsage') -> 'TokenUsage':
        return TokenUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            thinking_tokens=self.thinking_tokens + other.thinking_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
            model=self.model,
            latency_ms=max(self.latency_ms, other.latency_ms),
        )


def extract_token_usage(response, model: str, latency_ms: float) -> Optional[TokenUsage]:
    try:
        if hasattr(response, "usage_metadata"):
            m = response.usage_metadata
            prompt_tokens = getattr(m, "prompt_token_count", 0)
            completion_tokens = getattr(m, "candidates_token_count", 0)
            total_tokens = getattr(m, "total_token_count", 0)
            thinking_tokens = getattr(m, "thinking_token_count", 0)
            if thinking_tokens == 0 and total_tokens > prompt_tokens + completion_tokens:
                thinking_tokens = total_tokens - prompt_tokens - completion_tokens
            return TokenUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                thinking_tokens=thinking_tokens,
                total_tokens=total_tokens,
                model=model,
                latency_ms=latency_ms,
            )
    except Exception as e:
        logger.warning("提取 usage_metadata 失败: %s", e)
    return None
