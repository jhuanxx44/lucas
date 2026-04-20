"""Tests for LLMClient.chat_stream() streaming support."""
import pytest
from unittest.mock import MagicMock, patch


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

    mock_stream = [mock_chunk_1, mock_chunk_2, mock_chunk_end]

    with patch.dict("os.environ", {"OPENAI_API_KEY": "test", "OPENAI_BASE_URL": "http://fake"}):
        with patch("openai.OpenAI") as mock_openai:
            client = _OpenAICompatClient(model="deepseek-v3.2", system_prompt="test")
            mock_openai.return_value.chat.completions.create.return_value = iter(mock_stream)

            # Patch the internal _client to use our mock
            client._client = mock_openai.return_value

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
        with patch("openai.OpenAI"):
            client = _OpenAICompatClient(model="deepseek-v3.2", system_prompt=None)
            client._client = MagicMock()
            client._client.chat.completions.create.return_value = iter([mock_chunk])

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
        with patch("openai.OpenAI"):
            client = _OpenAICompatClient(model="deepseek-v3.2", system_prompt=None)
            client._client = MagicMock()
            client._client.chat.completions.create.return_value = iter([mock_chunk])

            chunks = []
            async for chunk in client.chat_stream(prompt="hi"):
                chunks.append(chunk)

            assert chunks == []
