"""业务工具：web_search / stock_quote / stock_kline / wiki_recall

只封装 utils/ 现有能力与 wiki 召回，不做任何"行为策略"判断
（何时搜索、如何组织查询、股票代码从哪来——由模型按 prompt 模板决定，
见 prompts/harness/tool-loop.md 的「业务工具使用策略」）。
"""
import logging
import re
from pathlib import Path

from harness.tools.base import ToolResult, ToolSpec
from utils.stock_data import format_kline, get_provider
from utils.web_search import search as _web_search
from utils.wiki_core import recall_wiki

logger = logging.getLogger(__name__)

MAX_SEARCH_RESULTS = 10
MAX_KLINE_COUNT = 120
MAX_RECALL_LIMIT = 5
RECALL_PAGE_CHARS = 3000

_CODE_RE = re.compile(r"(\d{6})(?:\.(SH|SZ))?", re.IGNORECASE)
_KLINE_PERIODS = {"daily", "weekly", "monthly", "1m", "5m", "15m", "30m", "60m"}


def _normalize_stock_code(raw) -> str | None:
    """接受 600519 / 600519.SH / 000001.SZ；后缀与市场矛盾时拒绝。返回 6 位数字代码。"""
    if not isinstance(raw, str):
        return None
    m = _CODE_RE.fullmatch(raw.strip())
    if not m:
        return None
    digits = m.group(1)
    suffix = (m.group(2) or "").upper()
    expected = "SH" if digits.startswith("6") else "SZ"
    if suffix and suffix != expected:
        return None
    return digits


_CODE_HINT = "code 必须是 6 位 A 股代码，可带 .SH/.SZ 后缀，如 600519 或 600519.SH"


async def web_search(workspace: Path, args: dict) -> ToolResult:
    query = args.get("query")
    if not isinstance(query, str) or not query.strip():
        return ToolResult(status="invalid_input", error_code="bad_args",
                          observation="query must be a non-empty string")
    max_results = args.get("max_results", 5)
    if not isinstance(max_results, int) or max_results <= 0:
        max_results = 5
    max_results = min(max_results, MAX_SEARCH_RESULTS)
    try:
        text = await _web_search(query.strip(), max_results)
    except Exception as e:
        return ToolResult(status="error", error_code="search_failed",
                          observation=f"{type(e).__name__}: {e}")
    if not text:
        return ToolResult(status="error", error_code="search_failed",
                          observation="搜索未返回结果（Tavily 与 DuckDuckGo 均无结果或不可用）")
    return ToolResult(status="ok", observation=text)


async def stock_quote(workspace: Path, args: dict) -> ToolResult:
    code = _normalize_stock_code(args.get("code"))
    if code is None:
        return ToolResult(status="invalid_input", error_code="bad_args",
                          observation=_CODE_HINT)
    try:
        quote = await get_provider().get_quote(code)
    except Exception as e:
        return ToolResult(status="error", error_code="quote_failed",
                          observation=f"{type(e).__name__}: {e}")
    if quote is None:
        return ToolResult(status="error", error_code="quote_unavailable",
                          observation=f"未获取到 {code} 的行情数据")
    return ToolResult(status="ok", observation=quote.to_markdown())


async def stock_kline(workspace: Path, args: dict) -> ToolResult:
    code = _normalize_stock_code(args.get("code"))
    if code is None:
        return ToolResult(status="invalid_input", error_code="bad_args",
                          observation=_CODE_HINT)
    period = args.get("period", "daily")
    if not isinstance(period, str) or period not in _KLINE_PERIODS:
        return ToolResult(status="invalid_input", error_code="bad_args",
                          observation=f"period 必须是 {sorted(_KLINE_PERIODS)} 之一，默认 daily")
    count = args.get("count", 30)
    if not isinstance(count, int) or count <= 0:
        count = 30
    count = min(count, MAX_KLINE_COUNT)
    try:
        bars = await get_provider().get_kline(code, period=period, count=count)
    except Exception as e:
        return ToolResult(status="error", error_code="kline_failed",
                          observation=f"{type(e).__name__}: {e}")
    if not bars:
        return ToolResult(status="error", error_code="kline_unavailable",
                          observation=f"未获取到 {code} 的 K 线数据")
    return ToolResult(status="ok", observation=format_kline(code, bars))


def wiki_recall(workspace: Path, args: dict) -> ToolResult:
    query = args.get("query")
    if not isinstance(query, str) or not query.strip():
        return ToolResult(status="invalid_input", error_code="bad_args",
                          observation="query must be a non-empty string")
    limit = args.get("limit", 3)
    if not isinstance(limit, int) or limit <= 0:
        limit = 3
    limit = min(limit, MAX_RECALL_LIMIT)
    # wiki 根目录固定为工作区下的 wiki/，召回内部再防索引条目路径逃逸
    wiki_root = workspace.resolve() / "wiki"
    if not wiki_root.is_dir():
        return ToolResult(status="ok", observation="（wiki 知识库为空，没有可召回的页面）")
    try:
        pages = recall_wiki(str(wiki_root), query.strip(),
                            limit=limit, max_chars=RECALL_PAGE_CHARS)
    except Exception as e:
        return ToolResult(status="error", error_code="recall_failed",
                          observation=f"{type(e).__name__}: {e}")
    if not pages:
        return ToolResult(status="ok",
                          observation=f"知识库中没有与「{query.strip()}」相关的页面")
    parts = []
    for page in pages:
        header = f"--- {page['name']}（{page['path']}） ---"
        body = page["content"] + ("\n…[truncated]" if page["truncated"] else "")
        parts.append(f"{header}\n{body}")
    return ToolResult(status="ok", observation="\n\n".join(parts))


WEB_SEARCH_SPEC = ToolSpec(
    name="web_search",
    description="联网搜索公开网页，返回编号、标题、链接、摘要的 markdown 列表",
    args_description='{"query": "搜索关键词", "max_results": "可选，默认 5，上限 10"}',
    handler=web_search,
)

STOCK_QUOTE_SPEC = ToolSpec(
    name="stock_quote",
    description="查询 A 股个股实时行情（最新价、涨跌幅、成交量、市盈率、市值等）",
    args_description='{"code": "6 位股票代码，可带 .SH/.SZ 后缀，如 600519 或 600519.SH"}',
    handler=stock_quote,
)

STOCK_KLINE_SPEC = ToolSpec(
    name="stock_kline",
    description="查询 A 股个股历史 K 线（开盘/收盘/最高/最低/成交量/涨跌幅）",
    args_description='{"code": "6 位股票代码，如 600519.SH", "period": "可选，daily/weekly/monthly/1m/5m/15m/30m/60m，默认 daily", "count": "可选，默认 30，上限 120"}',
    handler=stock_kline,
)

WIKI_RECALL_SPEC = ToolSpec(
    name="wiki_recall",
    description="从本地 wiki 知识库召回相关页面：先按索引（index.md）条目匹配，不足再全文检索；返回页面正文（每页最多 3000 字符）",
    args_description='{"query": "检索关键词，如公司名、行业、主题", "limit": "可选，返回页面数，默认 3，上限 5"}',
    handler=wiki_recall,
)

BUSINESS_TOOL_SPECS = [WEB_SEARCH_SPEC, STOCK_QUOTE_SPEC, STOCK_KLINE_SPEC, WIKI_RECALL_SPEC]
BUSINESS_TOOL_NAMES = [spec.name for spec in BUSINESS_TOOL_SPECS]
