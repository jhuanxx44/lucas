"""
Lucas LLM 统一调用层

对外只暴露一个入口：create_client(model) → LLMClient
根据模型名前缀自动路由到 Gemini / OpenAI 兼容客户端。

用法：
    from utils.llm_client import create_client

    client = create_client("gemini-3.1-pro", system_prompt="你是股市分析师")
    text, usage = await client.chat("分析宁德时代")

    client2 = create_client("deepseek-v3.2")
    text2, usage2 = await client2.chat("同样的问题")
"""
import os
import abc
import time
import asyncio
import logging
from typing import Optional, Tuple, List

from dotenv import load_dotenv

from utils.token_tracker import TokenUsage, extract_token_usage

load_dotenv()
logger = logging.getLogger(__name__)

# 路由规则：模型名前缀 → 客户端类型
_OPENAI_COMPAT_PREFIXES = ('glm-', 'ppio/', 'huawei/', 'zai/', 'MiniMax-', 'deepseek-', 'qwen', 'claude-')

# 特定模型前缀 → 独立的 API_KEY / BASE_URL 环境变量
_PROVIDER_ENV_OVERRIDES = {
    'MiniMax-': ('MINIMAX_API_KEY', 'MINIMAX_BASE_URL'),
}

MAX_RETRIES = 3
_RETRY_WAIT = [3, 5, 10]


def _is_retryable(e: Exception) -> bool:
    s = str(e).lower()
    return any(k in s for k in ['429', 'resource_exhausted', 'rate limit', '499', '500', '502', '503', '504'])


class LLMClient(abc.ABC):
    """统一接口：所有 LLM 客户端都实现这个协议"""

    def __init__(self, model: str, system_prompt: Optional[str] = None):
        self.model = model
        self.system_prompt = system_prompt

    @abc.abstractmethod
    async def chat(
        self,
        prompt: str,
        response_mime_type: str = "text/plain",
        temperature: Optional[float] = None,
        thinking_budget: Optional[int] = None,
    ) -> Tuple[str, Optional[TokenUsage]]:
        ...


class _GeminiClient(LLMClient):
    """Google Gemini，通过 GenAI SDK + 内部代理调用"""

    def __init__(self, model: str, system_prompt: Optional[str] = None,
                 enable_thinking: bool = True):
        super().__init__(model, system_prompt)
        self.enable_thinking = enable_thinking

        from google import genai
        api_key = os.environ.get("OPENAI_API_KEY")
        base_url = os.environ.get("OPENAI_BASE_URL", "")
        if not api_key:
            raise ValueError("OPENAI_API_KEY 未设置")
        self._client = genai.Client(
            api_key=api_key, vertexai=True,
            http_options={"base_url": f"{base_url}/gemini/", "timeout": 1200000},
        )

    async def chat(self, prompt: str, response_mime_type: str = "text/plain",
                   temperature: Optional[float] = None,
                   thinking_budget: Optional[int] = None) -> Tuple[str, Optional[TokenUsage]]:
        from google.genai import types

        contents = []
        if self.system_prompt:
            contents.append(types.Content(role="user", parts=[types.Part(text=self.system_prompt)]))
            contents.append(types.Content(role="model", parts=[types.Part(text="好的，我明白了。")]))
        contents.append(types.Content(role="user", parts=[types.Part(text=prompt)]))

        _budget = thinking_budget if thinking_budget is not None else 24576
        config = types.GenerateContentConfig(
            response_mime_type=response_mime_type,
            temperature=temperature if temperature is not None else 1.0,
            thinking_config=types.ThinkingConfig(
                thinking_budget=_budget if self.enable_thinking else 0
            ),
        )

        start = time.time()
        response = None
        for retry in range(MAX_RETRIES + 1):
            try:
                response = await self._client.aio.models.generate_content(
                    model=self.model, contents=contents, config=config
                )
            except Exception as e:
                if _is_retryable(e) and retry < MAX_RETRIES:
                    await asyncio.sleep(_RETRY_WAIT[retry])
                    continue
                raise
            if response and response.text:
                break
            if retry < MAX_RETRIES:
                await asyncio.sleep(_RETRY_WAIT[retry])

        latency = (time.time() - start) * 1000
        text = response.text if response and response.text else ""
        usage = extract_token_usage(response, self.model, latency) if response else None
        return text, usage


class _OpenAICompatClient(LLMClient):
    """OpenAI 兼容客户端，适用于 Zhipu/DeepSeek/Qwen 等"""

    def __init__(self, model: str, system_prompt: Optional[str] = None):
        super().__init__(model, system_prompt)
        import openai

        api_key = None
        base_url = None
        for prefix, (key_env, url_env) in _PROVIDER_ENV_OVERRIDES.items():
            if model.startswith(prefix):
                api_key = os.environ.get(key_env)
                base_url = os.environ.get(url_env)
                break

        if not api_key:
            api_key = os.environ.get("OPENAI_API_KEY")
        if not base_url:
            base_url = os.environ.get("OPENAI_BASE_URL", "")
        if not api_key:
            raise ValueError("API_KEY 未设置")
        self._client = openai.OpenAI(base_url=base_url, api_key=api_key)

    async def chat(self, prompt: str, response_mime_type: str = "text/plain",
                   temperature: Optional[float] = None,
                   thinking_budget: Optional[int] = None) -> Tuple[str, Optional[TokenUsage]]:
        messages = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        messages.append({"role": "user", "content": prompt})

        params = {
            "model": self.model,
            "messages": messages,
            "max_tokens": 65536,
            "temperature": temperature if temperature is not None else 1.0,
        }
        if response_mime_type == "application/json":
            params["response_format"] = {"type": "json_object"}

        response = await asyncio.to_thread(self._client.chat.completions.create, **params)

        text = ""
        if response.choices and response.choices[0].message.content:
            text = response.choices[0].message.content

        usage = None
        if hasattr(response, "usage") and response.usage:
            u = response.usage
            usage = TokenUsage(
                model=self.model,
                prompt_tokens=getattr(u, "prompt_tokens", 0) or 0,
                completion_tokens=getattr(u, "completion_tokens", 0) or 0,
                total_tokens=getattr(u, "total_tokens", 0) or 0,
            )
        return text, usage


def create_client(
    model: Optional[str] = None,
    system_prompt: Optional[str] = None,
    enable_thinking: bool = True,
) -> LLMClient:
    """
    工厂函数：根据模型名自动选择客户端。

    路由规则：
        glm-* / ppio/* / huawei/* / zai/* / MiniMax-* / deepseek-* / qwen-*  → OpenAI 兼容
        其余（gemini-* 等）→ Gemini SDK

    Args:
        model: 模型名，默认读 OPENAI_MODEL 环境变量
        system_prompt: 系统提示词
        enable_thinking: 是否启用思考模式（仅 Gemini 生效）
    """
    model = model or os.environ.get("OPENAI_MODEL", "gemini-3.1-pro")

    if any(model.startswith(p) for p in _OPENAI_COMPAT_PREFIXES):
        return _OpenAICompatClient(model=model, system_prompt=system_prompt)
    return _GeminiClient(model=model, system_prompt=system_prompt, enable_thinking=enable_thinking)
