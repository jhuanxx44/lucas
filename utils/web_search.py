"""
Web 搜索工具：多供应商抽象。
- auto（默认）：优先 Tavily，fallback 到 DuckDuckGo；
- tavily：通用搜索，覆盖中英文与全球网页；
- doubao：豆包搜索（火山引擎 Global 版），中文互联网信息质量高，返回来源与发布时间；
- duckduckgo：免 key 兜底搜索。
"""
import os
import asyncio
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

TAVILY_TIMEOUT_SECONDS = 90.0

# 豆包搜索（Global 版）参数：https://open.feedcoopapi.com/search_api/global_search
DOUBAO_SEARCH_URL = "https://open.feedcoopapi.com/search_api/global_search"
DOUBAO_SEARCH_TIMEOUT_SECONDS = 20.0
DOUBAO_MAX_DOC_COUNT = 20
DOUBAO_MAX_SNIPPET_LENGTH = 3000
DOUBAO_MAX_IMAGE_COUNT_PER_DOC = 1  # 图片摘要不做文本展示，传 1 减少响应体积

SEARCH_PROVIDERS = ("auto", "tavily", "doubao", "duckduckgo")


class SearchProviderError(Exception):
    """显式指定 provider 时，该供应商调用失败（携带对 Agent 可操作的中文原因）。"""


async def _tavily_search(query: str, max_results: int = 5, search_type: str = "general") -> Optional[str]:
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        return None
    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=api_key)
        topic = "news" if search_type == "news" else "general"
        resp = await asyncio.wait_for(
            asyncio.to_thread(
                client.search, query=query, max_results=max_results, topic=topic,
            ),
            timeout=TAVILY_TIMEOUT_SECONDS,
        )
        results = resp.get("results", [])
        if not results:
            return None
        parts = []
        for i, r in enumerate(results, 1):
            title = r.get("title", "")
            content = r.get("content", "")
            url = r.get("url", "")
            parts.append(f"{i}. [{title}]({url})\n   {content}")
        return "\n\n".join(parts)
    except asyncio.TimeoutError:
        logger.warning("Tavily 搜索超时 (%.0fs): %s", TAVILY_TIMEOUT_SECONDS, query[:80])
        return None
    except Exception as e:
        logger.warning("Tavily 搜索失败: %s", e)
        return None


async def _ddg_search(query: str, max_results: int = 5, search_type: str = "general", timeout: float = 15.0) -> Optional[str]:
    try:
        from ddgs import DDGS
        ddgs = DDGS(timeout=timeout)
        async def _do_search():
            if search_type == "news":
                raw = await asyncio.to_thread(ddgs.news, query, max_results=max_results, region="cn-zh")
            else:
                raw = await asyncio.to_thread(ddgs.text, query, max_results=max_results, region="cn-zh")
            return list(raw) if raw else []
        results = await asyncio.wait_for(_do_search(), timeout=timeout + 5)
        if not results:
            return None
        parts = []
        for i, r in enumerate(results, 1):
            title = r.get("title", "")
            body = r.get("body", r.get("description", ""))
            url = r.get("href", r.get("url", ""))
            parts.append(f"{i}. [{title}]({url})\n   {body}")
        return "\n\n".join(parts)
    except asyncio.TimeoutError:
        logger.warning("DuckDuckGo 搜索超时 (%.0fs): %s", timeout + 5, query[:80])
        return None
    except Exception as e:
        logger.warning("DuckDuckGo 搜索失败: %s", e)
        return None


async def _doubao_search(query: str, max_results: int = 10) -> str:
    """调用豆包搜索 Global 版，返回 markdown 结果列表；失败抛 SearchProviderError。

    无结果时返回空字符串。
    """
    api_key = os.environ.get("DOUBAO_SEARCH_API_KEY")
    if not api_key:
        raise SearchProviderError("豆包搜索未配置：缺少环境变量 DOUBAO_SEARCH_API_KEY")
    payload = {
        "Query": query,
        "DocCount": min(max_results, DOUBAO_MAX_DOC_COUNT),
        "MaxSnippetLength": min(500, DOUBAO_MAX_SNIPPET_LENGTH),
        "MaxImageCountPerDoc": DOUBAO_MAX_IMAGE_COUNT_PER_DOC,
    }
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        async with httpx.AsyncClient(
            timeout=DOUBAO_SEARCH_TIMEOUT_SECONDS, headers=headers,
        ) as client:
            response = await client.post(DOUBAO_SEARCH_URL, json=payload)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as e:
        raise SearchProviderError(
            f"豆包搜索 HTTP {e.response.status_code}：{e.response.text[:200]}"
        ) from e
    except httpx.HTTPError as e:
        raise SearchProviderError(f"豆包搜索网络错误：{type(e).__name__}: {e}") from e
    except ValueError as e:
        raise SearchProviderError(f"豆包搜索响应解析失败：{e}") from e

    metadata = data.get("ResponseMetadata") or {}
    error = metadata.get("Error")
    if error:
        code = error.get("Code") or error.get("CodeN")
        raise SearchProviderError(f"豆包搜索接口错误 {code}：{error.get('Message', '')}")

    result = data.get("Result")
    if not isinstance(result, dict):
        raise SearchProviderError("豆包搜索响应异常：Result 为空")
    if result.get("ErrorCode"):
        raise SearchProviderError(
            f"豆包搜索错误 {result.get('ErrorCode')}：{result.get('ErrorMsg', '')}"
        )

    documents = result.get("Documents") or []
    if not documents:
        return ""
    return _format_documents(documents)


def _format_documents(documents: list[dict]) -> str:
    parts = []
    for index, doc in enumerate(documents, 1):
        title = (doc.get("Title") or "").strip() or "无标题"
        url = doc.get("Url") or ""
        lines = [f"{index}. [{title}]({url})"]
        meta = []
        host_info = doc.get("HostInfo") or {}
        if host_info.get("Hostname"):
            meta.append(f"来源：{host_info['Hostname']}")
        doc_info = doc.get("DocumentInfo") or {}
        if doc_info.get("PublishTime"):
            meta.append(f"发布时间：{doc_info['PublishTime']}")
        if meta:
            lines.append("   " + "｜".join(meta))
        text_parts = [
            snippet["Text"].strip()
            for snippet in doc.get("Snippet") or []
            if isinstance(snippet, dict)
            and snippet.get("Type") == "text"
            and snippet.get("Text")
        ]
        body = "\n".join(text_parts).strip()
        if body:
            lines.append(f"   {body}")
        parts.append("\n".join(lines))
    return "\n\n".join(parts)


async def search(query: str, max_results: int = 5, provider: str = "auto") -> str:
    """按 provider 搜索：auto 时优先 Tavily，fallback DuckDuckGo。

    显式指定 doubao 且调用失败时抛 SearchProviderError（原因对 Agent 可操作）；
    其余 provider 失败返回空字符串。
    """
    if provider not in SEARCH_PROVIDERS:
        raise ValueError(f"unknown search provider: {provider}")
    if provider == "tavily":
        return await _tavily_search(query, max_results, "general") or ""
    if provider == "duckduckgo":
        return await _ddg_search(query, max_results, "general") or ""
    if provider == "doubao":
        return await _doubao_search(query, max_results)
    result = await _tavily_search(query, max_results, "general")
    if result:
        return result
    result = await _ddg_search(query, max_results, "general")
    return result or ""


async def search_news(query: str, max_results: int = 5) -> str:
    """新闻搜索：优先 Tavily news，fallback 到 DuckDuckGo 通用搜索（news 端点不稳定）"""
    result = await _tavily_search(query, max_results, "news")
    if result:
        return result
    result = await _ddg_search(query, max_results, "news")
    if result:
        return result
    return await search(query, max_results)
