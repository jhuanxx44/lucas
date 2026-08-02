import httpx
import pytest

from utils import doubao_search

SAMPLE_RESPONSE = {
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
                f"HTTP {self.status_code}", request=httpx.Request("POST", doubao_search.DOUBAO_SEARCH_URL),
                response=self,
            )

    def json(self):
        return self._payload


def _install_fake_client(monkeypatch, response):
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

    monkeypatch.setattr(doubao_search.httpx, "AsyncClient", FakeAsyncClient)
    return captured


@pytest.mark.asyncio
async def test_search_sends_correct_request_and_formats_markdown(monkeypatch):
    monkeypatch.setenv("DOUBAO_SEARCH_API_KEY", "test-key")
    captured = _install_fake_client(monkeypatch, _FakeResponse(SAMPLE_RESPONSE))

    result = await doubao_search.search("贵州茅台 半年报", max_results=5, max_snippet_length=300)

    assert captured["url"] == doubao_search.DOUBAO_SEARCH_URL
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert captured["payload"] == {
        "Query": "贵州茅台 半年报",
        "DocCount": 5,
        "MaxSnippetLength": 300,
        "MaxImageCountPerDoc": 1,
    }
    assert "1. [贵州茅台半年报前瞻](https://example.com/a)" in result
    assert "来源：雪球" in result
    assert "发布时间：2026-07-16T11:36:00+08:00" in result
    assert "预测营收 945 亿元" in result
    assert "归母净利润 470 亿元" in result
    assert "https://img.example.com/x.png" not in result


@pytest.mark.asyncio
async def test_search_missing_key_raises(monkeypatch):
    monkeypatch.delenv("DOUBAO_SEARCH_API_KEY", raising=False)
    with pytest.raises(doubao_search.DoubaoSearchError, match="DOUBAO_SEARCH_API_KEY"):
        await doubao_search.search("测试")


@pytest.mark.asyncio
async def test_search_metadata_error_raises(monkeypatch):
    monkeypatch.setenv("DOUBAO_SEARCH_API_KEY", "test-key")
    payload = {
        "ResponseMetadata": {
            "Error": {"CodeN": 10400, "Code": "10400", "Message": "query is empty"}
        },
        "Result": None,
    }
    _install_fake_client(monkeypatch, _FakeResponse(payload))
    with pytest.raises(doubao_search.DoubaoSearchError, match="10400.*query is empty"):
        await doubao_search.search("")


@pytest.mark.asyncio
async def test_search_result_error_code_raises(monkeypatch):
    monkeypatch.setenv("DOUBAO_SEARCH_API_KEY", "test-key")
    payload = {
        "ResponseMetadata": {"RequestId": "req-1"},
        "Result": {"ErrorCode": 700901, "ErrorMsg": "APIKey 无效"},
    }
    _install_fake_client(monkeypatch, _FakeResponse(payload))
    with pytest.raises(doubao_search.DoubaoSearchError, match="700901.*APIKey 无效"):
        await doubao_search.search("测试")


@pytest.mark.asyncio
async def test_search_empty_documents_returns_empty_string(monkeypatch):
    monkeypatch.setenv("DOUBAO_SEARCH_API_KEY", "test-key")
    payload = {
        "ResponseMetadata": {"RequestId": "req-1"},
        "Result": {"TotalDocCount": 0, "Documents": [], "ErrorCode": 0, "ErrorMsg": ""},
    }
    _install_fake_client(monkeypatch, _FakeResponse(payload))
    assert await doubao_search.search("冷门词") == ""


@pytest.mark.asyncio
async def test_search_http_status_error_raises(monkeypatch):
    monkeypatch.setenv("DOUBAO_SEARCH_API_KEY", "test-key")
    _install_fake_client(monkeypatch, _FakeResponse({}, status_code=429))
    with pytest.raises(doubao_search.DoubaoSearchError, match="HTTP 429"):
        await doubao_search.search("测试")


@pytest.mark.asyncio
async def test_search_network_error_raises(monkeypatch):
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

    monkeypatch.setattr(doubao_search.httpx, "AsyncClient", BoomClient)
    with pytest.raises(doubao_search.DoubaoSearchError, match="connection refused"):
        await doubao_search.search("测试")
