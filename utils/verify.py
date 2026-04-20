"""
研究员输出数据验证模块

三维校验：
1. URL 溯源 — 输出中的链接必须来自搜索结果
2. URL 可达性 — HEAD 请求验活
3. 财务数据交叉校验 — 输出中的数字 vs 传入的结构化数据
"""
import re
import asyncio
import logging
from datetime import datetime

import httpx

from agents.models import ResearchResult, VerificationResult, VerificationIssue

logger = logging.getLogger(__name__)

_MD_LINK_RE = re.compile(r'\[([^\]]*)\]\((https?://[^\s\)]+)\)')

_URL_HEAD_TIMEOUT = 3.0
_URL_CHECK_OVERALL_TIMEOUT = 10.0
_URL_CONCURRENCY = 5

_PRICE_TOLERANCE = 0.10
_PE_TOLERANCE = 0.20
_MARKET_CAP_TOLERANCE = 0.20
_EXTREME_TOLERANCE = 0.50

# ── 1. URL 溯源 ──────────────────────────────────────

def check_url_provenance(result: ResearchResult) -> list[VerificationIssue]:
    content_links = _MD_LINK_RE.findall(result.content)
    if not content_links:
        return []

    known_urls = {u["url"] for u in result.source_urls}
    issues = []
    for title, url in content_links:
        if url not in known_urls:
            issues.append(VerificationIssue(
                dimension="url_provenance",
                severity="error",
                message=f"疑似伪造链接: [{title}]({url}) 不在搜索结果中",
            ))
    return issues


# ── 2. URL 可达性 ─────────────────────────────────────

async def check_url_liveness(result: ResearchResult) -> list[VerificationIssue]:
    urls = [u["url"] for u in result.source_urls]
    if not urls:
        return []

    sem = asyncio.Semaphore(_URL_CONCURRENCY)
    issues = []

    async def _check_one(url: str, client: httpx.AsyncClient):
        async with sem:
            try:
                resp = await client.head(url, timeout=_URL_HEAD_TIMEOUT, follow_redirects=True)
                if resp.status_code >= 400:
                    issues.append(VerificationIssue(
                        dimension="url_liveness",
                        severity="warning",
                        message=f"链接不可达 (HTTP {resp.status_code}): {url}",
                    ))
            except (httpx.TimeoutException, httpx.ConnectError):
                issues.append(VerificationIssue(
                    dimension="url_liveness",
                    severity="info",
                    message=f"链接超时或连接失败: {url}",
                ))
            except Exception as e:
                issues.append(VerificationIssue(
                    dimension="url_liveness",
                    severity="info",
                    message=f"链接检查异常: {url} ({e})",
                ))

    try:
        async with httpx.AsyncClient() as client:
            tasks = [_check_one(url, client) for url in urls]
            await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=_URL_CHECK_OVERALL_TIMEOUT,
            )
    except asyncio.TimeoutError:
        issues.append(VerificationIssue(
            dimension="url_liveness",
            severity="info",
            message="URL 可达性检查整体超时，部分链接未验证",
        ))

    return issues


# ── 3. 财务数据交叉校验 ───────────────────────────────

_METRIC_CONFIG = {
    "最新价": {
        "content_patterns": [
            r'(?:最新价|收盘价|股价|现价)[^\d]*?([\d,]+\.?\d*)',
            r'([\d,]+\.?\d*)\s*元[^\d]*?(?:收盘|最新)',
        ],
        "tolerance": _PRICE_TOLERANCE,
        "label": "股价",
    },
    "市盈率": {
        "content_patterns": [
            r'(?:市盈率|PE|P/E)[^\d]*?([\d,]+\.?\d*)',
            r'([\d,]+\.?\d*)\s*倍[^\d]*?(?:PE|市盈率)',
        ],
        "tolerance": _PE_TOLERANCE,
        "label": "市盈率",
    },
    "总市值": {
        "content_patterns": [
            r'(?:总市值|市值)[^\d]*?([\d,]+\.?\d*)\s*(?:亿|万亿)',
        ],
        "tolerance": _MARKET_CAP_TOLERANCE,
        "label": "总市值",
    },
}


def _parse_market_data_table(market_data: str) -> dict[str, float]:
    """从结构化市场数据的 markdown 表格中提取数值"""
    result = {}
    for line in market_data.split("\n"):
        m = re.match(r'\|\s*(.+?)\s*\|\s*(.+?)\s*\|', line)
        if not m:
            continue
        key = m.group(1).strip()
        raw_val = m.group(2).strip()
        cleaned = re.sub(r'[%亿元倍万,]', '', raw_val)
        try:
            result[key] = float(cleaned)
        except ValueError:
            continue
    return result


def _extract_number(text: str, patterns: list[str]) -> list[float]:
    """用多个正则从文本中提取数字"""
    numbers = []
    for pat in patterns:
        for m in re.finditer(pat, text):
            raw = m.group(1).replace(",", "")
            try:
                numbers.append(float(raw))
            except ValueError:
                continue
    return numbers


def check_financial_data(result: ResearchResult) -> list[VerificationIssue]:
    if not result.market_data:
        return []

    source_data = _parse_market_data_table(result.market_data)
    if not source_data:
        return []

    issues = []
    for metric_key, cfg in _METRIC_CONFIG.items():
        source_val = source_data.get(metric_key)
        if not source_val or source_val == 0:
            continue

        content_vals = _extract_number(result.content, cfg["content_patterns"])
        for val in content_vals:
            if val == 0:
                continue
            deviation = abs(val - source_val) / source_val
            if deviation > _EXTREME_TOLERANCE:
                issues.append(VerificationIssue(
                    dimension="data_crosscheck",
                    severity="error",
                    message=(
                        f"{cfg['label']}严重偏差: 内容中为 {val}，"
                        f"数据源为 {source_val}，偏差 {deviation:.0%}"
                    ),
                ))
            elif deviation > cfg["tolerance"]:
                issues.append(VerificationIssue(
                    dimension="data_crosscheck",
                    severity="warning",
                    message=(
                        f"{cfg['label']}偏差: 内容中为 {val}，"
                        f"数据源为 {source_val}，偏差 {deviation:.0%}"
                    ),
                ))

    return issues


# ── 编排入口 ──────────────────────────────────────────

async def verify_result(result: ResearchResult) -> VerificationResult:
    """对单个 ResearchResult 执行全部校验，就地更新 verification 和 confidence"""
    all_issues = []

    all_issues.extend(check_url_provenance(result))
    all_issues.extend(check_financial_data(result))
    all_issues.extend(await check_url_liveness(result))

    vr = VerificationResult(
        issues=all_issues,
        checked_at=datetime.now().isoformat(timespec="seconds"),
    )
    result.verification = vr
    result.confidence = vr.compute_confidence()

    if vr.issues:
        logger.warning(
            "[%s] 验证发现 %d 个问题 (error=%d, warning=%d) → confidence=%s",
            result.researcher_name, len(vr.issues),
            vr.error_count, vr.warning_count, result.confidence,
        )
    else:
        logger.info("[%s] 验证通过 → confidence=high", result.researcher_name)

    return vr
