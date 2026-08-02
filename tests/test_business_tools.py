"""harness/tools 下的通用联网搜索与投研业务工具测试

web_search / stock_* 用 monkeypatch 替换真实网络与数据 provider；
wiki_recall 用临时 wiki 目录 fixture 验证索引优先、截断与全文 fallback。
"""
from pathlib import Path

import pytest

from harness.tools.base import ToolResult
from harness.tools.business.stock import STOCK_KLINE_SPEC, STOCK_QUOTE_SPEC
from harness.tools.business.wiki import WIKI_RECALL_SPEC
from harness.tools.generic.doubao_search import DOUBAO_SEARCH_SPEC
from harness.tools.generic.doubao_search import doubao_search as _doubao_handler
from harness.tools.generic.web_search import WEB_SEARCH_SPEC
from harness.tools.registry import ToolRuntime
from utils.doubao_search import DoubaoSearchError
from utils.stock_data import KlineBar, QuoteData

EXTERNAL_TOOL_SPECS = [
    WEB_SEARCH_SPEC,
    DOUBAO_SEARCH_SPEC,
    STOCK_QUOTE_SPEC,
    STOCK_KLINE_SPEC,
    WIKI_RECALL_SPEC,
]

PROJECT_ROOT = Path(__file__).resolve().parent.parent


async def _execute(tmp_path, spec, name, args, allowed=None):
    tools = ToolRuntime(tmp_path, [spec])
    return await tools.execute(name, args, allowed if allowed is not None else [name])


# ---------- web_search ----------

async def test_web_search_happy_path(tmp_path, monkeypatch):
    async def fake_search(query, max_results=5):
        assert query == "贵州茅台 2026 一季报"
        assert max_results == 5
        return "1. [贵州茅台一季报](https://example.com/q1)\n   营收增长"

    monkeypatch.setattr("harness.tools.generic.web_search._web_search", fake_search)
    result = await _execute(tmp_path, WEB_SEARCH_SPEC, "web_search",
                            {"query": "贵州茅台 2026 一季报"})
    assert result.status == "ok"
    assert "https://example.com/q1" in result.observation


async def test_web_search_empty_result_is_error(tmp_path, monkeypatch):
    async def fake_search(query, max_results=5):
        return ""

    monkeypatch.setattr("harness.tools.generic.web_search._web_search", fake_search)
    result = await _execute(tmp_path, WEB_SEARCH_SPEC, "web_search", {"query": "x"})
    assert result.status == "error"
    assert result.error_code == "search_failed"


async def test_web_search_exception_is_error_not_raised(tmp_path, monkeypatch):
    async def fake_search(query, max_results=5):
        raise ConnectionError("network down")

    monkeypatch.setattr("harness.tools.generic.web_search._web_search", fake_search)
    result = await _execute(tmp_path, WEB_SEARCH_SPEC, "web_search", {"query": "x"})
    assert result.status == "error"
    assert "network down" in result.observation


async def test_web_search_bad_args(tmp_path):
    result = await _execute(tmp_path, WEB_SEARCH_SPEC, "web_search", {"query": "  "})
    assert result.status == "invalid_input"


# ---------- doubao_search ----------

async def test_doubao_search_happy_path(tmp_path, monkeypatch):
    async def fake_search(query, max_results=10, max_snippet_length=500):
        assert query == "贵州茅台 2026 半年报"
        assert max_results == 8
        assert max_snippet_length == 300
        return "1. [贵州茅台半年报前瞻](https://example.com/q1)\n   来源：雪球"

    monkeypatch.setattr("harness.tools.generic.doubao_search._doubao_search", fake_search)
    result = await _execute(tmp_path, DOUBAO_SEARCH_SPEC, "doubao_search",
                            {"query": "贵州茅台 2026 半年报", "max_results": 8,
                             "max_snippet_length": 300})
    assert result.status == "ok"
    assert "https://example.com/q1" in result.observation


async def test_doubao_search_clamps_max_results(tmp_path, monkeypatch):
    seen = {}

    async def fake_search(query, max_results=10, max_snippet_length=500):
        seen["max_results"] = max_results
        seen["max_snippet_length"] = max_snippet_length
        return "结果"

    monkeypatch.setattr("harness.tools.generic.doubao_search._doubao_search", fake_search)
    # registry 的 schema 校验会先拒绝越界值，这里直接调 handler 验证防御性截断
    result = await _doubao_handler(tmp_path, {"query": "x", "max_results": 999,
                                              "max_snippet_length": 99999})
    assert result.status == "ok"
    assert seen == {"max_results": 20, "max_snippet_length": 3000}


async def test_doubao_search_empty_result_is_error(tmp_path, monkeypatch):
    async def fake_search(query, max_results=10, max_snippet_length=500):
        return ""

    monkeypatch.setattr("harness.tools.generic.doubao_search._doubao_search", fake_search)
    result = await _execute(tmp_path, DOUBAO_SEARCH_SPEC, "doubao_search", {"query": "x"})
    assert result.status == "error"
    assert result.error_code == "search_failed"
    assert "未返回结果" in result.observation


async def test_doubao_search_error_is_reported_not_raised(tmp_path, monkeypatch):
    async def fake_search(query, max_results=10, max_snippet_length=500):
        raise DoubaoSearchError("未配置豆包搜索 API Key")

    monkeypatch.setattr("harness.tools.generic.doubao_search._doubao_search", fake_search)
    result = await _execute(tmp_path, DOUBAO_SEARCH_SPEC, "doubao_search", {"query": "x"})
    assert result.status == "error"
    assert "API Key" in result.observation


async def test_doubao_search_bad_args(tmp_path):
    result = await _execute(tmp_path, DOUBAO_SEARCH_SPEC, "doubao_search", {"query": "  "})
    assert result.status == "invalid_input"


# ---------- stock_quote / stock_kline ----------

class _FakeProvider:
    def __init__(self, quote=None, bars=None):
        self._quote = quote
        self._bars = bars or []
        self.quote_calls = []
        self.kline_calls = []

    async def get_quote(self, code):
        self.quote_calls.append(code)
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
    monkeypatch.setattr("harness.tools.business.stock.get_provider", lambda: provider)
    result = await _execute(tmp_path, STOCK_QUOTE_SPEC, "stock_quote",
                            {"code": "600519.SH"})
    assert result.status == "ok"
    assert "贵州茅台" in result.observation
    assert "1500.0" in result.observation


async def test_stock_quote_provider_none_is_error(tmp_path, monkeypatch):
    provider = _FakeProvider(quote=None)
    monkeypatch.setattr("harness.tools.business.stock.get_provider", lambda: provider)
    result = await _execute(tmp_path, STOCK_QUOTE_SPEC, "stock_quote", {"code": "600519"})
    assert result.status == "error"
    assert result.error_code == "quote_unavailable"


async def test_stock_quote_rejects_bad_code(tmp_path):
    for bad in ("600519.SZ", "920001.SZ", "123456", "abcde", "6005190", {"x": 1}):
        result = await _execute(tmp_path, STOCK_QUOTE_SPEC, "stock_quote", {"code": bad})
        assert result.status == "invalid_input", bad


async def test_stock_quote_accepts_beijing_exchange_code(tmp_path, monkeypatch):
    provider = _FakeProvider(quote=_quote("920001"))
    monkeypatch.setattr("harness.tools.business.stock.get_provider", lambda: provider)

    result = await _execute(tmp_path, STOCK_QUOTE_SPEC, "stock_quote",
                            {"code": "920001.BJ"})

    assert result.status == "ok"
    assert provider.quote_calls == ["920001"]


async def test_stock_kline_happy_path(tmp_path, monkeypatch):
    provider = _FakeProvider(bars=_bars(5))
    monkeypatch.setattr("harness.tools.business.stock.get_provider", lambda: provider)
    result = await _execute(tmp_path, STOCK_KLINE_SPEC, "stock_kline",
                            {"code": "000001.SZ", "period": "weekly", "count": 5})
    assert result.status == "ok"
    assert "近5个交易日K线" in result.observation
    assert provider.kline_calls == [("000001", "weekly", 5)]


async def test_stock_kline_empty_is_error(tmp_path, monkeypatch):
    provider = _FakeProvider(bars=[])
    monkeypatch.setattr("harness.tools.business.stock.get_provider", lambda: provider)
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
    body = (
        "---\ntype: company\ntags: [白酒, 产能, 渠道]\n---\n"
        "贵州茅台是白酒龙头。\n" + "基酒产能与渠道库存分析。\n" * 400
    )
    (wiki / "companies" / "白酒" / "贵州茅台.md").write_text(body, encoding="utf-8")
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


async def test_wiki_recall_returns_all_matching_pages(tmp_path):
    wiki = tmp_path / "wiki"
    pages = wiki / "companies" / "白酒"
    pages.mkdir(parents=True)
    (wiki / "index.md").write_text(
        "# 知识库索引\n\n## 公司档案 · 白酒\n\n"
        + "".join(f"- [白酒公司{i}](companies/白酒/白酒公司{i}.md)\n" for i in range(6)),
        encoding="utf-8",
    )
    for i in range(6):
        (pages / f"白酒公司{i}.md").write_text(f"白酒公司{i}档案", encoding="utf-8")

    result = await _execute(tmp_path, WIKI_RECALL_SPEC, "wiki_recall", {"query": "白酒"})

    assert result.status == "ok"
    for i in range(6):
        assert f"白酒公司{i}" in result.observation


async def test_wiki_recall_skips_index_entries_escaping_wiki(tmp_path):
    _wiki_fixture(tmp_path)
    result = await _execute(tmp_path, WIKI_RECALL_SPEC, "wiki_recall",
                            {"query": "逃逸页面"})
    assert result.status == "ok"
    assert "SECRET-OUTSIDE-WIKI" not in result.observation
    assert "没有" in result.observation  # 无合法命中


async def test_wiki_recall_skips_symlink_page_escaping_wiki(tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    outside = tmp_path.parent / f"{tmp_path.name}-wiki-secret.md"
    outside.write_text("AlphaEscape 外部秘密", encoding="utf-8")
    (wiki / "leak.md").symlink_to(outside)

    result = await _execute(tmp_path, WIKI_RECALL_SPEC, "wiki_recall",
                            {"query": "AlphaEscape"})

    assert result.status == "ok"
    assert "外部秘密" not in result.observation


async def test_wiki_recall_denies_wiki_root_symlink_escape(tmp_path):
    outside = tmp_path.parent / f"{tmp_path.name}-outside-wiki"
    outside.mkdir()
    (outside / "secret.md").write_text("RootEscape 外部秘密", encoding="utf-8")
    (tmp_path / "wiki").symlink_to(outside, target_is_directory=True)

    result = await _execute(tmp_path, WIKI_RECALL_SPEC, "wiki_recall",
                            {"query": "RootEscape"})

    assert result.status == "denied"
    assert result.error_code == "path_escape"


async def test_wiki_recall_missing_wiki_dir(tmp_path):
    result = await _execute(tmp_path, WIKI_RECALL_SPEC, "wiki_recall", {"query": "茅台"})
    assert result.status == "ok"
    assert "知识库为空" in result.observation


async def test_wiki_recall_bad_args(tmp_path):
    result = await _execute(tmp_path, WIKI_RECALL_SPEC, "wiki_recall", {"query": ""})
    assert result.status == "invalid_input"


async def test_wiki_recall_sees_page_written_after_first_recall(tmp_path):
    """第一次 recall 后写入的页面，第二次 recall 必须能命中（索引不得缓存过期）。"""
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    first = await _execute(tmp_path, WIKI_RECALL_SPEC, "wiki_recall", {"query": "光放大器"})
    assert "没有" in first.observation

    (wiki / "光放大器.md").write_text(
        "---\ntitle: 光放大器\nsummary: 掺铒光放大器是光纤通信的关键器件。\n---\n\n正文。",
        encoding="utf-8")
    second = await _execute(tmp_path, WIKI_RECALL_SPEC, "wiki_recall", {"query": "光放大器"})
    assert "光放大器（光放大器.md）" in second.observation


async def test_wiki_recall_reflects_overwritten_content(tmp_path):
    """覆盖已有页面后，新内容可命中、已移除的旧内容不再命中。"""
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    page = wiki / "某页.md"
    page.write_text("本文介绍波分复用，一种光纤传输技术。", encoding="utf-8")
    result = await _execute(tmp_path, WIKI_RECALL_SPEC, "wiki_recall", {"query": "波分复用"})
    assert "某页" in result.observation

    page.write_text("本文介绍掺铒光放大器，一种光器件。", encoding="utf-8")
    result = await _execute(tmp_path, WIKI_RECALL_SPEC, "wiki_recall", {"query": "光放大器"})
    assert "某页" in result.observation
    result = await _execute(tmp_path, WIKI_RECALL_SPEC, "wiki_recall", {"query": "波分复用"})
    assert "某页" not in result.observation


async def test_wiki_recall_stops_returning_deleted_page(tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    page = wiki / "某页.md"
    page.write_text("本文介绍波分复用，一种光纤传输技术。", encoding="utf-8")
    result = await _execute(tmp_path, WIKI_RECALL_SPEC, "wiki_recall", {"query": "波分复用"})
    assert "某页" in result.observation

    page.unlink()
    result = await _execute(tmp_path, WIKI_RECALL_SPEC, "wiki_recall", {"query": "波分复用"})
    assert "某页" not in result.observation


async def test_wiki_recall_matches_entity_without_punctuation_boundary(tmp_path):
    """实体名以无标点分隔的形式出现时也必须命中（不依赖分词词典，如"台积电"）。"""
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "台积电.md").write_text("台积电主导先进制程。", encoding="utf-8")
    result = await _execute(tmp_path, WIKI_RECALL_SPEC, "wiki_recall", {"query": "台积电"})
    assert "台积电（台积电.md）" in result.observation


@pytest.mark.parametrize(
    ("task_id", "query", "expected_paths"),
    [
        ("WIKI-01", "澄海精密 2025 年第四季度一次良率", ["companies/机械设备/澄海精密.md"]),
        ("WIKI-02", "688559 2025 年度现金分红方案", ["notes/688559-2025年度分红公告.md"]),
        (
            "WIKI-03",
            "凌波设备与远川装备 2025 年末标准设备年产能",
            ["companies/机械设备/凌波设备.md", "companies/机械设备/远川装备.md"],
        ),
    ],
)
async def test_wiki_eval_fixtures_recall_expected_pages(task_id, query, expected_paths):
    workspace = PROJECT_ROOT / "evals" / "tasks" / task_id / "fixture"

    result = await _execute(
        workspace,
        WIKI_RECALL_SPEC,
        "wiki_recall",
        {"query": query},
    )

    assert result.status == "ok"
    for expected_path in expected_paths:
        assert expected_path in result.observation


async def test_wiki_recall_prefers_summary_over_raw_content(tmp_path):
    """有 frontmatter.summary 时返回摘要而非截取正文。"""
    wiki = tmp_path / "wiki"
    (wiki / "companies" / "白酒").mkdir(parents=True)
    (wiki / "index.md").write_text(
        "# 知识库索引\n\n## 公司档案 · 白酒\n\n"
        "- [贵州茅台](companies/白酒/贵州茅台.md)\n",
        encoding="utf-8",
    )
    body = (
        "---\ntitle: 贵州茅台\ntype: company\n"
        "summary: 贵州茅台是A股白酒龙头，2025年营收约1800亿，渠道改革持续推进。\n"
        "---\n"
        "贵州茅台是白酒龙头。\n" + "基酒产能与渠道库存分析。\n" * 400
    )
    (wiki / "companies" / "白酒" / "贵州茅台.md").write_text(body, encoding="utf-8")

    result = await _execute(tmp_path, WIKI_RECALL_SPEC, "wiki_recall",
                            {"query": "贵州茅台 产能"})
    assert result.status == "ok"
    # 返回的是摘要，不是正文截取
    assert "A股白酒龙头" in result.observation
    assert "2025年营收约1800亿" in result.observation
    # 不应出现截断标记
    assert "…[truncated]" not in result.observation
    # 原始正文不在返回中
    assert "基酒产能与渠道库存分析" not in result.observation


async def test_wiki_recall_falls_back_to_content_when_no_summary(tmp_path):
    """无 frontmatter.summary 时回退到正文截取（向后兼容）。"""
    wiki = tmp_path / "wiki"
    (wiki / "companies" / "白酒").mkdir(parents=True)
    (wiki / "index.md").write_text(
        "# 知识库索引\n\n## 公司档案 · 白酒\n\n"
        "- [贵州茅台](companies/白酒/贵州茅台.md)\n",
        encoding="utf-8",
    )
    body = (
        "---\ntype: company\ntags: [白酒, 产能, 渠道]\n---\n"
        "贵州茅台是白酒龙头。\n" + "基酒产能与渠道库存分析。\n" * 400
    )
    (wiki / "companies" / "白酒" / "贵州茅台.md").write_text(body, encoding="utf-8")

    result = await _execute(tmp_path, WIKI_RECALL_SPEC, "wiki_recall",
                            {"query": "贵州茅台 产能"})
    assert result.status == "ok"
    assert "…[truncated]" in result.observation
    assert "基酒产能与渠道库存分析" in result.observation


# ---------- 白名单 ----------

async def test_business_tools_denied_when_not_in_whitelist(tmp_path):
    for spec in EXTERNAL_TOOL_SPECS:
        tools = ToolRuntime(tmp_path, [spec])
        result = await tools.execute(spec.name, {"query": "x", "code": "600519"}, [])
        assert result.status == "denied", spec.name
        assert result.error_code == "tool_not_allowed"


# ---------- adapter 装配 ----------

async def test_adapter_executes_explicitly_allowed_business_tool(tmp_path):
    """任务白名单显式允许业务工具时，adapter 注册并真实执行。"""
    import json
    from evals.harness.adapters.lucas_single import LucasSingleAgent
    from harness.models import FunctionCall, ModelTurn, RunLimits
    from harness.trace import TraceRecorder

    _wiki_fixture(tmp_path)

    class FakeModel:
        def __init__(self):
            self.responses = [
                ModelTurn(
                    function_calls=[FunctionCall(
                        call_id="call-1", name="wiki_recall",
                        arguments={"query": "600519 分红"}, summary="查询相关公告",
                    )],
                    response_items=[{
                        "type": "function_call", "call_id": "call-1",
                        "name": "wiki_recall",
                        "arguments": json.dumps({
                            "query": "600519 分红", "summary": "查询相关公告",
                        }, ensure_ascii=False),
                    }],
                ),
                ModelTurn(output_text="done"),
            ]

        async def complete(self, request):
            return self.responses.pop(0)

    adapter = LucasSingleAgent(model_adapter=FakeModel())
    trace = TraceRecorder(tmp_path / "trace.jsonl", "run-test")
    result = await adapter.run("查公告", tmp_path, ["read_file", "wiki_recall"],
                               RunLimits(max_steps=5, timeout_seconds=30), trace)
    assert result.finish_reason == "completed"
    assert result.answer == "done"


async def test_adapter_does_not_force_business_tools_into_task_whitelist(tmp_path):
    """注册工具不等于授权；task 未允许的业务工具必须被 ToolRuntime 拒绝。"""
    import json
    from evals.harness.adapters.lucas_single import LucasSingleAgent
    from harness.models import FunctionCall, ModelTurn, RunLimits
    from harness.trace import TraceRecorder, read_trace

    _wiki_fixture(tmp_path)

    class FakeModel:
        def __init__(self):
            self.responses = [
                ModelTurn(
                    function_calls=[FunctionCall(
                        call_id="call-1", name="wiki_recall",
                        arguments={"query": "600519 分红"}, summary="查询相关公告",
                    )],
                    response_items=[{
                        "type": "function_call", "call_id": "call-1",
                        "name": "wiki_recall",
                        "arguments": json.dumps({
                            "query": "600519 分红", "summary": "查询相关公告",
                        }, ensure_ascii=False),
                    }],
                ),
                ModelTurn(output_text="工具不可用"),
            ]

        async def complete(self, request):
            return self.responses.pop(0)

    adapter = LucasSingleAgent(model_adapter=FakeModel())
    trace_path = tmp_path / "trace.jsonl"
    result = await adapter.run(
        "查公告", tmp_path, ["read_file"],
        RunLimits(max_steps=5, timeout_seconds=30),
        TraceRecorder(trace_path, "run-test"),
    )

    assert result.finish_reason == "completed"
    errors = [event for event in read_trace(trace_path)
              if event["event"] == "tool_call_error"]
    assert errors[0]["data"] == {
        "tool_call_id": "call-1",
        "status": "denied",
        "error_code": "tool_not_allowed",
    }
