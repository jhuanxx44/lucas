import sys
from datetime import datetime
from types import SimpleNamespace

import pytest

from utils.stock_data import TDXMCPProvider


class FallbackProvider:
    async def get_quote(self, code):
        return None

    async def get_kline(self, code, period="daily", count=30):
        return []

    async def get_financials(self, code):
        return []

    async def get_north_flow(self, count=10):
        return []

    async def get_sector_flow(self, top_n=15):
        return []


@pytest.fixture
def fake_tdx_server(monkeypatch):
    server = SimpleNamespace()

    def symbol_info(market, code):
        assert market == 0
        assert code == "300308"
        return {
            "code": code,
            "name": "中际旭创",
            "time": datetime(2026, 6, 4, 14, 59),
            "open": 1250.0,
            "high": 1290.0,
            "low": 1241.36,
            "close": 1279.96,
            "pre_close": 1275.0,
            "vol": 213647,
            "amount": 27147362304.0,
            "turnover": 1.925,
            "avg": 1270.66,
        }

    def stock_kline(market, code, period, start, count, times, adjust_type):
        assert market == 0
        assert code == "300308"
        assert period == 4
        assert start == 0
        assert times == 1
        assert adjust_type == "qfq"
        return [
            {
                "datetime": datetime(2026, 6, 3, 15, 0),
                "open": 12200.0,
                "close": 12750.0,
                "high": 13200.0,
                "low": 12200.0,
                "vol": 34525076.0,
            },
            {
                "datetime": datetime(2026, 6, 4, 15, 0),
                "open": 12500.0,
                "close": 12799.6,
                "high": 12900.0,
                "low": 12413.6,
                "vol": 21364700.0,
            },
        ]

    server.symbol_info = symbol_info
    server.stock_kline = stock_kline
    monkeypatch.setitem(sys.modules, "mcpServer", server)
    return server


@pytest.mark.asyncio
async def test_tdx_mcp_quote(fake_tdx_server):
    provider = TDXMCPProvider(fallback=FallbackProvider())

    quote = await provider.get_quote("300308")

    assert quote.name == "中际旭创"
    assert quote.price == 1279.96
    assert quote.change_pct == 0.39
    assert quote.extra["数据源"] == "tdx-mcp"


@pytest.mark.asyncio
async def test_tdx_mcp_kline_normalizes_price_scale(fake_tdx_server):
    provider = TDXMCPProvider(fallback=FallbackProvider())

    bars = await provider.get_kline("300308", count=2)

    assert [bar.date for bar in bars] == ["2026-06-03", "2026-06-04"]
    assert bars[-1].open == 1250.0
    assert bars[-1].close == 1279.96
    assert bars[-1].high == 1290.0
    assert bars[-1].low == 1241.36
