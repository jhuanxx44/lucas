"""A 股实时行情与历史 K 线工具。"""
import re
from pathlib import Path

from harness.tools.base import ToolResult, ToolSpec
from utils.stock_data import format_kline, get_provider

MAX_KLINE_COUNT = 120

_CODE_RE = re.compile(r"(\d{6})(?:\.(SH|SZ|BJ))?", re.IGNORECASE)
_KLINE_PERIODS = {"daily", "weekly", "monthly", "1m", "5m", "15m", "30m", "60m"}


def _normalize_stock_code(raw) -> str | None:
    """校验沪深北 A 股代码及可选市场后缀，返回 6 位数字代码。"""
    if not isinstance(raw, str):
        return None
    match = _CODE_RE.fullmatch(raw.strip())
    if not match:
        return None
    digits = match.group(1)
    suffix = (match.group(2) or "").upper()
    if digits.startswith("6"):
        expected = "SH"
    elif digits.startswith(("0", "3")):
        expected = "SZ"
    elif digits.startswith(("4", "8", "92")):
        expected = "BJ"
    else:
        return None
    if suffix and suffix != expected:
        return None
    return digits


_CODE_HINT = "code 必须是 6 位 A 股代码，可带 .SH/.SZ/.BJ 后缀，如 600519.SH 或 920001.BJ"


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


STOCK_QUOTE_SPEC = ToolSpec(
    name="stock_quote",
    description="查询 A 股个股实时行情（最新价、涨跌幅、成交量、市盈率、市值等）",
    args_description='{"code": "6 位股票代码，可带 .SH/.SZ/.BJ 后缀，如 600519.SH 或 920001.BJ；按常识给出，不要臆造不存在的代码"}',
    handler=stock_quote,
)

STOCK_KLINE_SPEC = ToolSpec(
    name="stock_kline",
    description="查询 A 股个股历史 K 线（开盘/收盘/最高/最低/成交量/涨跌幅）",
    args_description='{"code": "6 位股票代码，如 600519.SH 或 920001.BJ，不要臆造不存在的代码", "period": "可选，daily/weekly/monthly/1m/5m/15m/30m/60m，默认 daily", "count": "可选，默认 30，上限 120"}',
    handler=stock_kline,
)
