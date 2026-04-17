"""
Web 搜索工具：优先 Tavily，fallback 到 DuckDuckGo
"""
import os
import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)


async def _tavily_search(query: str, max_results: int = 5, search_type: str = "general") -> Optional[str]:
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        return None
    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=api_key)
        topic = "news" if search_type == "news" else "general"
        resp = await asyncio.to_thread(
            client.search, query=query, max_results=max_results, topic=topic,
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
    except Exception as e:
        logger.warning("Tavily 搜索失败: %s", e)
        return None


async def _ddg_search(query: str, max_results: int = 5, search_type: str = "general") -> Optional[str]:
    try:
        from ddgs import DDGS
        ddgs = DDGS()
        if search_type == "news":
            raw = await asyncio.to_thread(ddgs.news, query, max_results=max_results, region="cn-zh")
        else:
            raw = await asyncio.to_thread(ddgs.text, query, max_results=max_results, region="cn-zh")
        results = list(raw) if raw else []
        if not results:
            return None
        parts = []
        for i, r in enumerate(results, 1):
            title = r.get("title", "")
            body = r.get("body", r.get("description", ""))
            url = r.get("href", r.get("url", ""))
            parts.append(f"{i}. [{title}]({url})\n   {body}")
        return "\n\n".join(parts)
    except Exception as e:
        logger.warning("DuckDuckGo 搜索失败: %s", e)
        return None


async def search(query: str, max_results: int = 5) -> str:
    """通用搜索：优先 Tavily，fallback DuckDuckGo"""
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
