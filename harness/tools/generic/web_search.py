"""公共互联网搜索工具。"""
from pathlib import Path

from harness.tools.base import ToolResult, ToolSpec
from utils.web_search import search as _web_search

MAX_SEARCH_RESULTS = 10


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
        result = await _web_search(query.strip(), max_results)
    except Exception as e:
        return ToolResult(status="error", error_code="search_failed",
                          observation=f"{type(e).__name__}: {e}")
    if not result:
        return ToolResult(status="error", error_code="search_failed",
                          observation="搜索未返回结果（Tavily 与 DuckDuckGo 均无结果或不可用）")
    return ToolResult(status="ok", observation=result)


WEB_SEARCH_SPEC = ToolSpec(
    name="web_search",
    description="联网搜索公开网页，返回编号、标题、链接、摘要的 markdown 列表",
    args_description='{"query": "搜索关键词，用具体词组（主体+主题+时间范围），不要把整句问题原样丢进去", "max_results": "可选，默认 5，上限 10"}',
    handler=web_search,
)
