import asyncio
import sys
from types import SimpleNamespace

import httpx
import pytest

from utils import web_search


SAMPLE_DOUBAO_RESPONSE = {
    "ResponseMetadata": {"RequestId": "req-1"},
    "Result": {
        "TotalDocCount": 20,
        "Documents": [
            {
                "Rank": 0,
                "Url": "https://example.com/a",
                "Title": "贵州茅台半年报前瞻",
                "Snippet": [
                    {"Type": "text", "Text": "预测营收 945 亿元\n"},
                    {"Type": "image", "Image": {"ImageUrl": "https://img.example.com/x.png"}},
                    {"Type": "text", "Text": "归母净利润 470 亿元"},
                ],
                "DocumentInfo": {"Filetype": "webpage", "PublishTime": "2026-07-16T11:36:00+08:00"},
                "HostInfo": {"Hostname": "雪球"},
            }
        ],
        "ErrorCode": 0,
        "ErrorMsg": "",
    },
}


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = ""

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=httpx.Request("POST", web_search.DOUBAO_SEARCH_URL),
                response=self,
            )

    def json(self):
        return self._payload


def _install_fake_httpx_client(monkeypatch, response):
    captured = {}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            captured["headers"] = kwargs.get("headers")
            captured["timeout"] = kwargs.get("timeout")

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, json=None):
            captured["url"] = url
            captured["payload"] = json
            return response

    monkeypatch.setattr(web_search.httpx, "AsyncClient", FakeAsyncClient)
    return captured


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


# ---------- doubao provider ----------

@pytest.mark.asyncio
async def test_doubao_provider_sends_correct_request_and_formats_markdown(monkeypatch):
    monkeypatch.setenv("DOUBAO_SEARCH_API_KEY", "test-key")
    captured = _install_fake_httpx_client(monkeypatch, _FakeResponse(SAMPLE_DOUBAO_RESPONSE))

    result = await web_search.search("贵州茅台 半年报", max_results=5, provider="doubao")

    assert captured["url"] == web_search.DOUBAO_SEARCH_URL
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert captured["payload"] == {
        "Query": "贵州茅台 半年报",
        "DocCount": 5,
        "MaxSnippetLength": 500,
        "MaxImageCountPerDoc": 1,
    }
    assert "1. [贵州茅台半年报前瞻](https://example.com/a)" in result
    assert "来源：雪球" in result
    assert "发布时间：2026-07-16T11:36:00+08:00" in result
    assert "预测营收 945 亿元" in result
    assert "归母净利润 470 亿元" in result
    assert "https://img.example.com/x.png" not in result


@pytest.mark.asyncio
async def test_doubao_provider_missing_key_raises(monkeypatch):
    monkeypatch.delenv("DOUBAO_SEARCH_API_KEY", raising=False)
    with pytest.raises(web_search.SearchProviderError, match="DOUBAO_SEARCH_API_KEY"):
        await web_search.search("测试", provider="doubao")


@pytest.mark.asyncio
async def test_doubao_provider_metadata_error_raises(monkeypatch):
    monkeypatch.setenv("DOUBAO_SEARCH_API_KEY", "test-key")
    payload = {
        "ResponseMetadata": {
            "Error": {"CodeN": 10400, "Code": "10400", "Message": "query is empty"}
        },
        "Result": None,
    }
    _install_fake_httpx_client(monkeypatch, _FakeResponse(payload))
    with pytest.raises(web_search.SearchProviderError, match="10400.*query is empty"):
        await web_search.search("", provider="doubao")


@pytest.mark.asyncio
async def test_doubao_provider_result_error_code_raises(monkeypatch):
    monkeypatch.setenv("DOUBAO_SEARCH_API_KEY", "test-key")
    payload = {
        "ResponseMetadata": {"RequestId": "req-1"},
        "Result": {"ErrorCode": 700901, "ErrorMsg": "APIKey 无效"},
    }
    _install_fake_httpx_client(monkeypatch, _FakeResponse(payload))
    with pytest.raises(web_search.SearchProviderError, match="700901.*APIKey 无效"):
        await web_search.search("测试", provider="doubao")


@pytest.mark.asyncio
async def test_doubao_provider_empty_documents_returns_empty_string(monkeypatch):
    monkeypatch.setenv("DOUBAO_SEARCH_API_KEY", "test-key")
    payload = {
        "ResponseMetadata": {"RequestId": "req-1"},
        "Result": {"TotalDocCount": 0, "Documents": [], "ErrorCode": 0, "ErrorMsg": ""},
    }
    _install_fake_httpx_client(monkeypatch, _FakeResponse(payload))
    assert await web_search.search("冷门词", provider="doubao") == ""


@pytest.mark.asyncio
async def test_doubao_provider_http_status_error_raises(monkeypatch):
    monkeypatch.setenv("DOUBAO_SEARCH_API_KEY", "test-key")
    _install_fake_httpx_client(monkeypatch, _FakeResponse({}, status_code=429))
    with pytest.raises(web_search.SearchProviderError, match="HTTP 429"):
        await web_search.search("测试", provider="doubao")


@pytest.mark.asyncio
async def test_doubao_provider_network_error_raises(monkeypatch):
    monkeypatch.setenv("DOUBAO_SEARCH_API_KEY", "test-key")

    class BoomClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, json=None):
            raise httpx.ConnectError("connection refused", request=httpx.Request("POST", url))

    monkeypatch.setattr(web_search.httpx, "AsyncClient", BoomClient)
    with pytest.raises(web_search.SearchProviderError, match="connection refused"):
        await web_search.search("测试", provider="doubao")


# ---------- provider 路由 ----------

@pytest.mark.asyncio
async def test_search_routes_explicit_provider(monkeypatch):
    seen = {}

    async def fake_tavily(query, max_results=5, search_type="general"):
        seen["tavily"] = (query, max_results, search_type)
        return "tavily result"

    async def fake_ddg(query, max_results=5, search_type="general", timeout=15.0):
        seen["ddg"] = (query, max_results, search_type)
        return "ddg result"

    async def fake_doubao(query, max_results=10):
        seen["doubao"] = (query, max_results)
        return "doubao result"

    monkeypatch.setattr(web_search, "_tavily_search", fake_tavily)
    monkeypatch.setattr(web_search, "_ddg_search", fake_ddg)
    monkeypatch.setattr(web_search, "_doubao_search", fake_doubao)

    assert await web_search.search("q", 3, "tavily") == "tavily result"
    assert await web_search.search("q", 3, "duckduckgo") == "ddg result"
    assert await web_search.search("q", 3, "doubao") == "doubao result"
    assert seen["tavily"] == ("q", 3, "general")
    assert seen["ddg"] == ("q", 3, "general")
    assert seen["doubao"] == ("q", 3)


@pytest.mark.asyncio
async def test_search_auto_falls_back_to_ddg(monkeypatch):
    async def fake_tavily(query, max_results=5, search_type="general"):
        return ""

    async def fake_ddg(query, max_results=5, search_type="general", timeout=15.0):
        return "ddg result"

    monkeypatch.setattr(web_search, "_tavily_search", fake_tavily)
    monkeypatch.setattr(web_search, "_ddg_search", fake_ddg)
    assert await web_search.search("q") == "ddg result"


@pytest.mark.asyncio
async def test_search_invalid_provider_raises_value_error():
    with pytest.raises(ValueError, match="unknown search provider"):
        await web_search.search("q", provider="bing")
