"""Tests for LLMClient.chat_stream() streaming support."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def test_default_client_uses_deepseek_v4_flash_and_deepseek_env():
    from utils.llm_client import _OpenAICompatClient, create_client

    env = {
        "DEEPSEEK_API_KEY": "deepseek-key",
        "DEEPSEEK_BASE_URL": "https://deepseek.example/v1",
    }
    with patch.dict("os.environ", env, clear=True):
        with patch("openai.AsyncOpenAI") as mock_openai:
            client = create_client()

    assert isinstance(client, _OpenAICompatClient)
    assert client.model == "deepseek-v4-flash"
    mock_openai.assert_called_once_with(
        base_url="https://deepseek.example/v1",
        api_key="deepseek-key",
    )


@pytest.mark.asyncio
async def test_gemini_chat_stream_awaits_sdk_stream():
    from utils.llm_client import _GeminiClient

    async def chunks():
        for text in ("你好", "世界"):
            yield MagicMock(text=text)

    client = object.__new__(_GeminiClient)
    client.model = "gemini-3.1-pro"
    client.system_prompt = None
    client.enable_thinking = False
    client._client = MagicMock()
    client._client.aio.models.generate_content_stream = AsyncMock(return_value=chunks())

    result = []
    async for chunk in client.chat_stream(prompt="hi"):
        result.append(chunk)

    assert result == ["你好", "世界"]


@pytest.mark.asyncio
async def test_openai_chat_stream_yields_chunks():
    from utils.llm_client import _OpenAICompatClient

    mock_chunk_1 = MagicMock()
    mock_chunk_1.choices = [MagicMock()]
    mock_chunk_1.choices[0].delta.content = "你好"

    mock_chunk_2 = MagicMock()
    mock_chunk_2.choices = [MagicMock()]
    mock_chunk_2.choices[0].delta.content = "世界"

    mock_chunk_end = MagicMock()
    mock_chunk_end.choices = [MagicMock()]
    mock_chunk_end.choices[0].delta.content = None

    async def mock_stream():
        for chunk in (mock_chunk_1, mock_chunk_2, mock_chunk_end):
            yield chunk

    with patch.dict("os.environ", {"OPENAI_API_KEY": "test", "OPENAI_BASE_URL": "http://fake"}):
        with patch("openai.AsyncOpenAI") as mock_openai:
            client = _OpenAICompatClient(model="deepseek-v3.2", system_prompt="test")
            client._client.chat.completions.create = AsyncMock(return_value=mock_stream())

            chunks = []
            async for chunk in client.chat_stream(prompt="hi"):
                chunks.append(chunk)

            assert "你好" in chunks
            assert "世界" in chunks


@pytest.mark.asyncio
async def test_openai_chat_stream_strips_think_tags():
    from utils.llm_client import _OpenAICompatClient

    mock_chunk = MagicMock()
    mock_chunk.choices = [MagicMock()]
    mock_chunk.choices[0].delta.content = "<think>internal reasoning</think>visible text"

    with patch.dict("os.environ", {"OPENAI_API_KEY": "test", "OPENAI_BASE_URL": "http://fake"}):
        with patch("openai.AsyncOpenAI"):
            client = _OpenAICompatClient(model="deepseek-v3.2", system_prompt=None)
            async def mock_stream():
                yield mock_chunk
            client._client.chat.completions.create = AsyncMock(return_value=mock_stream())

            chunks = []
            async for chunk in client.chat_stream(prompt="hi"):
                chunks.append(chunk)

            assert chunks == ["visible text"]


@pytest.mark.asyncio
async def test_openai_chat_stream_skips_empty_after_strip():
    from utils.llm_client import _OpenAICompatClient

    mock_chunk = MagicMock()
    mock_chunk.choices = [MagicMock()]
    mock_chunk.choices[0].delta.content = "<think>only thinking</think>"

    with patch.dict("os.environ", {"OPENAI_API_KEY": "test", "OPENAI_BASE_URL": "http://fake"}):
        with patch("openai.AsyncOpenAI"):
            client = _OpenAICompatClient(model="deepseek-v3.2", system_prompt=None)
            async def mock_stream():
                yield mock_chunk
            client._client.chat.completions.create = AsyncMock(return_value=mock_stream())

            chunks = []
            async for chunk in client.chat_stream(prompt="hi"):
                chunks.append(chunk)

            assert chunks == []
