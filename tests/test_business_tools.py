"""harness/tools/business.py 业务工具测试

web_search / stock_* 用 monkeypatch 替换真实网络与数据 provider；
wiki_recall 用临时 wiki 目录 fixture 验证索引优先、截断与全文 fallback。
"""
import pytest

from harness.tools.base import ToolResult
from harness.tools.business import (
    BUSINESS_TOOL_SPECS,
    STOCK_KLINE_SPEC,
    STOCK_QUOTE_SPEC,
    WEB_SEARCH_SPEC,
    WIKI_RECALL_SPEC,
)
from harness.tools.registry import ToolRuntime
from utils.stock_data import KlineBar, QuoteData


async def _execute(tmp_path, spec, name, args, allowed=None):
    tools = ToolRuntime(tmp_path, [spec])
    return await tools.execute(name, args, allowed if allowed is not None else [name])


# ---------- web_search ----------

async def test_web_search_happy_path(tmp_path, monkeypatch):
    async def fake_search(query, max_results=5):
        assert query == "贵州茅台 2026 一季报"
        assert max_results == 5
        return "1. [贵州茅台一季报](https://example.com/q1)\n   营收增长"

    monkeypatch.setattr("harness.tools.business._web_search", fake_search)
    result = await _execute(tmp_path, WEB_SEARCH_SPEC, "web_search",
                            {"query": "贵州茅台 2026 一季报"})
    assert result.status == "ok"
    assert "https://example.com/q1" in result.observation


async def test_web_search_empty_result_is_error(tmp_path, monkeypatch):
    async def fake_search(query, max_results=5):
        return ""

    monkeypatch.setattr("harness.tools.business._web_search", fake_search)
    result = await _execute(tmp_path, WEB_SEARCH_SPEC, "web_search", {"query": "x"})
    assert result.status == "error"
    assert result.error_code == "search_failed"


async def test_web_search_exception_is_error_not_raised(tmp_path, monkeypatch):
    async def fake_search(query, max_results=5):
        raise ConnectionError("network down")

    monkeypatch.setattr("harness.tools.business._web_search", fake_search)
    result = await _execute(tmp_path, WEB_SEARCH_SPEC, "web_search", {"query": "x"})
    assert result.status == "error"
    assert "network down" in result.observation


async def test_web_search_bad_args(tmp_path):
    result = await _execute(tmp_path, WEB_SEARCH_SPEC, "web_search", {"query": "  "})
    assert result.status == "invalid_input"


# ---------- stock_quote / stock_kline ----------

class _FakeProvider:
    def __init__(self, quote=None, bars=None):
        self._quote = quote
        self._bars = bars or []
        self.kline_calls = []

    async def get_quote(self, code):
        return self._quote

    async def get_kline(self, code, period="daily", count=30):
        self.kline_calls.append((code, period, count))
        return self._bars


def _quote(code="600519"):
    return QuoteData(code=code, name="贵州茅台", price=1500.0, change_pct=1.5)


def _bars(n=3):
    return [
        KlineBar(date=f"2026-07-1{i}", open=100 + i, close=101 + i,
                 high=102 + i, low=99 + i, volume=1000)
        for i in range(n)
    ]


async def test_stock_quote_happy_path(tmp_path, monkeypatch):
    provider = _FakeProvider(quote=_quote())
    monkeypatch.setattr("harness.tools.business.get_provider", lambda: provider)
    result = await _execute(tmp_path, STOCK_QUOTE_SPEC, "stock_quote",
                            {"code": "600519.SH"})
    assert result.status == "ok"
    assert "贵州茅台" in result.observation
    assert "1500.0" in result.observation


async def test_stock_quote_provider_none_is_error(tmp_path, monkeypatch):
    provider = _FakeProvider(quote=None)
    monkeypatch.setattr("harness.tools.business.get_provider", lambda: provider)
    result = await _execute(tmp_path, STOCK_QUOTE_SPEC, "stock_quote", {"code": "600519"})
    assert result.status == "error"
    assert result.error_code == "quote_unavailable"


async def test_stock_quote_rejects_bad_code(tmp_path):
    for bad in ("600519.SZ", "abcde", "6005190", {"x": 1}):
        result = await _execute(tmp_path, STOCK_QUOTE_SPEC, "stock_quote", {"code": bad})
        assert result.status == "invalid_input", bad


async def test_stock_kline_happy_path(tmp_path, monkeypatch):
    provider = _FakeProvider(bars=_bars(5))
    monkeypatch.setattr("harness.tools.business.get_provider", lambda: provider)
    result = await _execute(tmp_path, STOCK_KLINE_SPEC, "stock_kline",
                            {"code": "000001.SZ", "period": "weekly", "count": 5})
    assert result.status == "ok"
    assert "近5个交易日K线" in result.observation
    assert provider.kline_calls == [("000001", "weekly", 5)]


async def test_stock_kline_empty_is_error(tmp_path, monkeypatch):
    provider = _FakeProvider(bars=[])
    monkeypatch.setattr("harness.tools.business.get_provider", lambda: provider)
    result = await _execute(tmp_path, STOCK_KLINE_SPEC, "stock_kline", {"code": "600519"})
    assert result.status == "error"
    assert result.error_code == "kline_unavailable"


async def test_stock_kline_rejects_bad_period(tmp_path):
    result = await _execute(tmp_path, STOCK_KLINE_SPEC, "stock_kline",
                            {"code": "600519", "period": "yearly"})
    assert result.status == "invalid_input"


# ---------- wiki_recall ----------

def _wiki_fixture(root):
    """wiki fixture：index.md 两个条目 + 一个未索引页面 + 一个索引外逃逸页面"""
    wiki = root / "wiki"
    (wiki / "companies" / "白酒").mkdir(parents=True)
    (wiki / "notes").mkdir(parents=True)
    (wiki / "index.md").write_text(
        "# 知识库索引\n\n"
        "## 公司档案 · 白酒\n\n"
        "- [贵州茅台](companies/白酒/贵州茅台.md)\n"
        "- [五粮液](companies/白酒/五粮液.md)\n"
        "- [逃逸页面](../escape.md)\n",
        encoding="utf-8",
    )
    long_body = "贵州茅台是白酒龙头。\n" + "基酒产能与渠道库存分析。\n" * 400  # > 3000 字符
    (wiki / "companies" / "白酒" / "贵州茅台.md").write_text(long_body, encoding="utf-8")
    (wiki / "companies" / "白酒" / "五粮液.md").write_text("浓香型白酒。", encoding="utf-8")
    (wiki / "notes" / "600519-公告.md").write_text("600519 分红公告摘要", encoding="utf-8")
    (root / "escape.md").write_text("SECRET-OUTSIDE-WIKI", encoding="utf-8")
    return wiki


async def test_wiki_recall_index_first_and_truncates(tmp_path):
    _wiki_fixture(tmp_path)
    result = await _execute(tmp_path, WIKI_RECALL_SPEC, "wiki_recall",
                            {"query": "贵州茅台 产能"})
    assert result.status == "ok"
    assert "--- 贵州茅台（companies/白酒/贵州茅台.md） ---" in result.observation
    # 页面超过 3000 字符被截断并标注
    assert "…[truncated]" in result.observation
    page_body = result.observation.split("---\n", 1)[1]
    assert len(page_body) < 3100
    # 五粮液与查询无关，未被召回
    assert "五粮液" not in result.observation


async def test_wiki_recall_fulltext_fallback_when_index_misses(tmp_path):
    _wiki_fixture(tmp_path)
    # "600519" 只出现在未索引的 notes 页面里，索引条目无命中 → 走全文 fallback
    result = await _execute(tmp_path, WIKI_RECALL_SPEC, "wiki_recall",
                            {"query": "600519 分红"})
    assert result.status == "ok"
    assert "600519-公告" in result.observation
    assert "分红公告摘要" in result.observation


async def test_wiki_recall_skips_index_entries_escaping_wiki(tmp_path):
    _wiki_fixture(tmp_path)
    result = await _execute(tmp_path, WIKI_RECALL_SPEC, "wiki_recall",
                            {"query": "逃逸页面"})
    assert result.status == "ok"
    assert "SECRET-OUTSIDE-WIKI" not in result.observation
    assert "没有" in result.observation  # 无合法命中


async def test_wiki_recall_missing_wiki_dir(tmp_path):
    result = await _execute(tmp_path, WIKI_RECALL_SPEC, "wiki_recall", {"query": "茅台"})
    assert result.status == "ok"
    assert "知识库为空" in result.observation


async def test_wiki_recall_bad_args(tmp_path):
    result = await _execute(tmp_path, WIKI_RECALL_SPEC, "wiki_recall", {"query": ""})
    assert result.status == "invalid_input"


# ---------- 白名单 ----------

async def test_business_tools_denied_when_not_in_whitelist(tmp_path):
    for spec in BUSINESS_TOOL_SPECS:
        tools = ToolRuntime(tmp_path, [spec])
        result = await tools.execute(spec.name, {"query": "x", "code": "600519"}, [])
        assert result.status == "denied", spec.name
        assert result.error_code == "tool_not_allowed"


# ---------- adapter 装配 ----------

async def test_adapter_registers_business_tools_by_default(tmp_path):
    """任务白名单只给 read_file 时，业务工具仍默认全开并真实执行"""
    import json
    from evals.harness.adapters.lucas_single import LucasSingleAgent
    from harness.models import RunLimits
    from harness.trace import TraceRecorder

    _wiki_fixture(tmp_path)

    class FakeModel:
        def __init__(self):
            self.responses = [
                json.dumps({"action": "tool", "tool": "wiki_recall",
                            "args": {"query": "600519 分红"}}),
                json.dumps({"action": "answer", "reply": "done"}),
            ]

        async def complete(self, prompt):
            return self.responses.pop(0), None

    adapter = LucasSingleAgent(model_adapter=FakeModel())
    trace = TraceRecorder(tmp_path / "trace.jsonl", "run-test")
    result = await adapter.run("查公告", tmp_path, ["read_file"],
                               RunLimits(max_steps=5, timeout_seconds=30), trace)
    assert result.finish_reason == "completed"
    assert result.answer == "done"
