import asyncio
import sys
from types import SimpleNamespace

import pytest

from utils import web_search


@pytest.mark.asyncio
async def test_tavily_search_has_explicit_generous_timeout(monkeypatch):
    seen = {}

    class FakeTavilyClient:
        def __init__(self, api_key):
            assert api_key == "test-key"

        def search(self, **kwargs):
            return {"results": []}

    async def fake_to_thread(function, **kwargs):
        return function(**kwargs)

    original_wait_for = asyncio.wait_for

    async def recording_wait_for(awaitable, timeout):
        seen["timeout"] = timeout
        return await original_wait_for(awaitable, timeout)

    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    monkeypatch.setitem(
        sys.modules,
        "tavily",
        SimpleNamespace(TavilyClient=FakeTavilyClient),
    )
    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(asyncio, "wait_for", recording_wait_for)

    assert await web_search._tavily_search("半导体设备") is None
    assert seen["timeout"] == web_search.TAVILY_TIMEOUT_SECONDS
    assert web_search.TAVILY_TIMEOUT_SECONDS >= 60
