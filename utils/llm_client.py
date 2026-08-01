"""DeepSeek official Responses API transport.

Lucas deliberately supports one LLM protocol: OpenAI Responses as exposed by
the DeepSeek official endpoint. Agent decisions are normalized in
``harness.model_adapter``; simple knowledge/corpus calls use ``generate_text``.
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any, Callable
from urllib.parse import urlparse

from dotenv import load_dotenv

from utils.token_tracker import TokenUsage

load_dotenv()

DEFAULT_MODEL = "deepseek-v4-flash"
DEFAULT_BASE_URL = "https://api.deepseek.com"
MAX_RETRIES = 3
_RETRY_WAIT = (3, 5, 10)


def _is_retryable(error: Exception) -> bool:
    status = getattr(error, "status_code", None)
    if status == 429 or isinstance(status, int) and status >= 500:
        return True
    text = str(error).lower()
    return any(
        marker in text
        for marker in (
            "429", "rate limit", "500", "502", "503", "504",
            "connection error", "connection reset", "timed out", "timeout",
        )
    )


def _usage_field(usage: Any, *names: str) -> int:
    """从 usage 对象/字典中取第一个非空候选字段（兼容两种 API 命名）。"""
    for name in names:
        value = usage.get(name) if isinstance(usage, dict) else getattr(usage, name, None)
        if value:
            return int(value)
    return 0


def _has_field(usage: Any, name: str) -> bool:
    return name in usage if isinstance(usage, dict) else getattr(usage, name, None) is not None


def responses_usage(response: Any, model: str, latency_ms: float = 0.0) -> TokenUsage | None:
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    # DeepSeek Responses 端点同时兼容 OpenAI Responses 命名
    # （input_tokens/output_tokens）与 Chat Completions 命名
    # （prompt_tokens/completion_tokens），两者都要能解析。
    prompt_tokens = _usage_field(usage, "input_tokens", "prompt_tokens")
    # OpenAI 风格 output_tokens 包含 reasoning，需减去；
    # DeepSeek 风格 completion_tokens 已剔除 reasoning，不能再减。
    openai_style = _has_field(usage, "output_tokens")
    output_tokens = _usage_field(usage, "output_tokens", "completion_tokens")
    output_details = (
        usage.get("output_tokens_details")
        if isinstance(usage, dict) else getattr(usage, "output_tokens_details", None)
    )
    reasoning_tokens = _usage_field(output_details, "reasoning_tokens")
    if reasoning_tokens == 0:
        completion_details = (
            usage.get("completion_tokens_details")
            if isinstance(usage, dict) else getattr(usage, "completion_tokens_details", None)
        )
        reasoning_tokens = _usage_field(completion_details, "reasoning_tokens")
    if reasoning_tokens == 0:
        reasoning_tokens = _usage_field(usage, "reasoning_tokens")
    return TokenUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=max(0, output_tokens - reasoning_tokens) if openai_style else output_tokens,
        thinking_tokens=reasoning_tokens,
        total_tokens=_usage_field(usage, "total_tokens"),
        model=model,
        latency_ms=latency_ms,
    )


class DeepSeekResponsesClient:
    """Small transport wrapper around ``AsyncOpenAI.responses``."""

    def __init__(self, model: str | None = None, instructions: str | None = None):
        from openai import AsyncOpenAI

        api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        base_url = os.environ.get("DEEPSEEK_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
        if not api_key:
            raise ValueError("DEEPSEEK_API_KEY 未设置")
        parsed_base_url = urlparse(base_url)
        if parsed_base_url.scheme != "https" or parsed_base_url.hostname != "api.deepseek.com":
            raise ValueError("DEEPSEEK_BASE_URL 必须使用 HTTPS 并指向 DeepSeek 官网 api.deepseek.com")
        configured_model = model.strip() if isinstance(model, str) else ""
        environment_model = os.environ.get("DEEPSEEK_MODEL", "").strip()
        self.model = configured_model or environment_model or DEFAULT_MODEL
        self.instructions = instructions
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def create(
        self,
        *,
        input: str | list[dict[str, Any]],
        instructions: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        text: dict[str, Any] | None = None,
        stream: bool = False,
        max_output_tokens: int = 65_536,
        on_retry: Callable[[dict[str, Any]], None] | None = None,
    ):
        params: dict[str, Any] = {
            "model": self.model,
            "input": input,
            "max_output_tokens": max_output_tokens,
            "temperature": temperature,
            "stream": stream,
        }
        effective_instructions = instructions if instructions is not None else self.instructions
        if effective_instructions:
            params["instructions"] = effective_instructions
        if tools:
            params.update(
                tools=tools,
                tool_choice="auto",
                parallel_tool_calls=False,
            )
        if text is not None:
            params["text"] = text

        for retry in range(MAX_RETRIES + 1):
            try:
                return await self._client.responses.create(**params)
            except Exception as error:
                if retry >= MAX_RETRIES or not _is_retryable(error):
                    raise
                delay_seconds = _RETRY_WAIT[retry]
                if on_retry is not None:
                    on_retry({
                        "retry_count": retry + 1,
                        "next_attempt": retry + 2,
                        "delay_seconds": delay_seconds,
                        "error_type": type(error).__name__,
                        "status_code": getattr(error, "status_code", None),
                    })
                await asyncio.sleep(delay_seconds)
        raise AssertionError("unreachable")

    async def generate_text(
        self,
        prompt: str,
        *,
        response_mime_type: str = "text/plain",
        temperature: float = 0.0,
        instructions: str | None = None,
    ) -> tuple[str, TokenUsage | None]:
        text_format = None
        if response_mime_type == "application/json":
            text_format = {"format": {"type": "json_object"}}
        started = time.monotonic()
        response = await self.create(
            input=prompt,
            instructions=instructions,
            temperature=temperature,
            text=text_format,
        )
        latency_ms = (time.monotonic() - started) * 1000
        return response.output_text or "", responses_usage(response, self.model, latency_ms)


def create_client(
    model: str | None = None,
    instructions: str | None = None,
) -> DeepSeekResponsesClient:
    return DeepSeekResponsesClient(model=model, instructions=instructions)
