"""
股票数据工具：provider 抽象 + AKShare 默认实现

数据源可替换：实现 StockDataProvider 接口即可。
"""
import re
import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# ── 数据模型 ──────────────────────────────────────────

@dataclass
class QuoteData:
    code: str
    name: str = ""
    price: float = 0.0
    change_pct: float = 0.0
    volume: float = 0.0
    turnover: float = 0.0
    pe: float = 0.0
    pb: float = 0.0
    market_cap: float = 0.0
    extra: dict = field(default_factory=dict)

    def to_markdown(self) -> str:
        lines = [
            f"### {self.name}（{self.code}）实时行情",
            "| 指标 | 数值 |", "|------|------|",
            f"| 最新价 | {self.price} |",
            f"| 涨跌幅 | {self.change_pct}% |",
            f"| 成交量 | {self.volume} |",
            f"| 成交额 | {self.turnover} |",
            f"| 市盈率 | {self.pe} |",
            f"| 市净率 | {self.pb} |",
            f"| 总市值 | {self.market_cap} |",
        ]
        for k, v in self.extra.items():
            lines.append(f"| {k} | {v} |")
        return "\n".join(lines)


@dataclass
class KlineBar:
    date: str
    open: float
    close: float
    high: float
    low: float
    volume: float
    change_pct: float = 0.0


@dataclass
class FinancialRow:
    period: str
    data: dict


@dataclass
class FlowRecord:
    date: str
    value: float
    label: str = ""


# ── Provider 接口 ──────────────────────────────────────

class StockDataProvider(ABC):
    @abstractmethod
    async def get_quote(self, code: str) -> Optional[QuoteData]: ...

    @abstractmethod
    async def get_kline(self, code: str, period: str = "daily", count: int = 30) -> list[KlineBar]: ...

    @abstractmethod
    async def get_financials(self, code: str) -> list[FinancialRow]: ...

    @abstractmethod
    async def get_north_flow(self, count: int = 10) -> list[FlowRecord]: ...

    @abstractmethod
    async def get_sector_flow(self, top_n: int = 15) -> list[FlowRecord]: ...


# ── AKShare 实现 ──────────────────────────────────────

class AKShareProvider(StockDataProvider):

    def _code_prefix(self, code: str) -> str:
        """300/00 开头 → sz，6 开头 → sh"""
        if code.startswith("6"):
            return f"sh{code}"
        return f"sz{code}"

    async def get_quote(self, code: str) -> Optional[QuoteData]:
        """腾讯行情接口（快且稳定）"""
        try:
            import urllib.request
            symbol = self._code_prefix(code)
            url = f"http://qt.gtimg.cn/q={symbol}"
            resp = await asyncio.to_thread(
                lambda: urllib.request.urlopen(url, timeout=5).read().decode("gbk")
            )
            # 格式: v_sz300750="51~宁德时代~300750~444.20~453.98~..."
            parts = resp.split("~")
            if len(parts) < 50:
                return None
            return QuoteData(
                code=code,
                name=parts[1],
                price=float(parts[3]),
                change_pct=float(parts[32]),
                volume=float(parts[36]),
                turnover=float(parts[37]),
                pe=float(parts[39]) if parts[39] else 0.0,
                pb=0.0,
                market_cap=float(parts[45]) * 1e4 if parts[45] else 0.0,
                extra={
                    "涨跌额": parts[31],
                    "今开": parts[5],
                    "最高": parts[33],
                    "最低": parts[34],
                    "昨收": parts[4],
                    "换手率": f"{parts[38]}%",
                    "流通市值": f"{parts[44]}亿",
                    "总市值": f"{parts[45]}亿",
                },
            )
        except Exception as e:
            logger.warning("腾讯行情 get_quote 失败 %s: %s", code, e)
            return None

    async def get_kline(self, code: str, period: str = "daily", count: int = 30) -> list[KlineBar]:
        try:
            import akshare as ak
            symbol = self._code_prefix(code)
            df = await asyncio.to_thread(
                ak.stock_zh_a_daily, symbol=symbol, adjust="qfq",
            )
            if df is None or df.empty:
                return []
            df = df.tail(count)
            return [
                KlineBar(
                    date=str(r.get("date", "")),
                    open=float(r.get("open", 0)),
                    close=float(r.get("close", 0)),
                    high=float(r.get("high", 0)),
                    low=float(r.get("low", 0)),
                    volume=float(r.get("volume", 0)),
                    change_pct=round((float(r.get("close", 0)) / float(r.get("open", 1)) - 1) * 100, 2)
                    if float(r.get("open", 0)) > 0 else 0.0,
                )
                for _, r in df.iterrows()
            ]
        except Exception as e:
            logger.warning("AKShare get_kline 失败 %s: %s", code, e)
            return []

    async def get_financials(self, code: str) -> list[FinancialRow]:
        try:
            import akshare as ak
            df = await asyncio.to_thread(
                ak.stock_financial_abstract_ths, symbol=code, indicator="按年度",
            )
            if df is None or df.empty:
                return []
            return [
                FinancialRow(period=str(r.iloc[0]), data=r.to_dict())
                for _, r in df.head(4).iterrows()
            ]
        except Exception as e:
            logger.warning("AKShare get_financials 失败 %s: %s", code, e)
            return []

    async def get_north_flow(self, count: int = 10) -> list[FlowRecord]:
        try:
            import akshare as ak
            df = await asyncio.to_thread(ak.stock_hsgt_fund_flow_summary_em)
            if df is None or df.empty:
                return []
            north = df[df["资金方向"] == "北向"]
            records = []
            for _, r in north.iterrows():
                records.append(FlowRecord(
                    date=str(r.get("交易日", "")),
                    value=float(r.get("成交净买额", 0)),
                    label=f"{r.get('板块', '')}({r.get('类型', '')})",
                ))
            return records
        except Exception as e:
            logger.warning("AKShare get_north_flow 失败: %s", e)
            return []

    async def get_sector_flow(self, top_n: int = 15) -> list[FlowRecord]:
        """行业资金流向 — 东方财富接口不稳定，返回空让搜索兜底"""
        try:
            import akshare as ak
            df = await asyncio.to_thread(
                ak.stock_sector_fund_flow_rank, indicator="今日", sector_type="行业资金流",
            )
            if df is None or df.empty:
                return []
            return [
                FlowRecord(
                    date="",
                    value=float(r.get("主力净流入-净额", r.get("主力净流入", 0))),
                    label=str(r.get("名称", "")),
                )
                for _, r in df.head(top_n).iterrows()
            ]
        except Exception as e:
            logger.warning("AKShare get_sector_flow 失败（可能被代理拦截）: %s", e)
            return []


# ── 格式化工具 ──────────────────────────────────────

def format_kline(code: str, bars: list[KlineBar]) -> str:
    if not bars:
        return ""
    lines = [f"### {code} 近{len(bars)}个交易日K线"]
    lines.append("| 日期 | 开盘 | 收盘 | 最高 | 最低 | 成交量 | 涨跌幅 |")
    lines.append("|------|------|------|------|------|--------|--------|")
    for b in bars:
        lines.append(f"| {b.date} | {b.open} | {b.close} | {b.high} | {b.low} | {b.volume} | {b.change_pct}% |")
    return "\n".join(lines)


def format_financials(code: str, rows: list[FinancialRow]) -> str:
    if not rows:
        return ""
    cols = list(rows[0].data.keys())
    lines = [f"### {code} 近年财务摘要"]
    lines.append("| " + " | ".join(cols) + " |")
    lines.append("|" + "|".join(["------"] * len(cols)) + "|")
    for row in rows:
        lines.append("| " + " | ".join(str(row.data.get(c, "-")) for c in cols) + " |")
    return "\n".join(lines)


def format_north_flow(records: list[FlowRecord]) -> str:
    if not records:
        return ""
    lines = ["### 近期北向资金净流入", "| 日期 | 净流入（亿） |", "|------|-------------|"]
    for r in records:
        lines.append(f"| {r.date} | {r.value:.2f} |")
    return "\n".join(lines)


def format_sector_flow(records: list[FlowRecord]) -> str:
    if not records:
        return ""
    lines = ["### 今日行业资金流向", "| 行业 | 主力净流入 |", "|------|-----------|"]
    for r in records:
        lines.append(f"| {r.label} | {r.value} |")
    return "\n".join(lines)


# ── 名称映射 ──────────────────────────────────────

_NAME_TO_CODE = {
    "宁德时代": "300750", "贵州茅台": "600519", "比亚迪": "002594",
    "中国平安": "601318", "招商银行": "600036", "隆基绿能": "601012",
    "药明康德": "603259", "中芯国际": "688981",
}


def extract_stock_codes(text: str) -> list[str]:
    codes = re.findall(r'\b([036]\d{5})\b', text)
    for name, code in _NAME_TO_CODE.items():
        if name in text:
            codes.append(code)
    return list(dict.fromkeys(codes))


# ── 统一入口 ──────────────────────────────────────

_default_provider: Optional[StockDataProvider] = None


def get_provider() -> StockDataProvider:
    global _default_provider
    if _default_provider is None:
        _default_provider = AKShareProvider()
    return _default_provider


def set_provider(provider: StockDataProvider):
    global _default_provider
    _default_provider = provider


async def get_stock_data(question: str, data_types: list[str]) -> str:
    codes = extract_stock_codes(question)
    provider = get_provider()
    parts = []

    for dtype in data_types:
        if dtype == "quote" and codes:
            for code in codes:
                q = await provider.get_quote(code)
                if q:
                    parts.append(q.to_markdown())
        elif dtype == "kline" and codes:
            for code in codes:
                bars = await provider.get_kline(code, count=20)
                if bars:
                    parts.append(format_kline(code, bars))
        elif dtype == "financials" and codes:
            for code in codes:
                rows = await provider.get_financials(code)
                if rows:
                    parts.append(format_financials(code, rows))
        elif dtype == "north_flow":
            records = await provider.get_north_flow()
            if records:
                parts.append(format_north_flow(records))
        elif dtype == "sector_flow":
            records = await provider.get_sector_flow()
            if records:
                parts.append(format_sector_flow(records))

    return "\n\n".join(parts)
