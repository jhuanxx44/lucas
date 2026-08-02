"""豆包搜索（Global 版）联网搜索工具。"""
from pathlib import Path

from harness.tools.base import ToolResult, ToolSpec
from utils.doubao_search import DoubaoSearchError, search as _doubao_search

MAX_SEARCH_RESULTS = 20
MAX_SNIPPET_LENGTH = 3000


async def doubao_search(workspace: Path, args: dict) -> ToolResult:
    query = args.get("query")
    if not isinstance(query, str) or not query.strip():
        return ToolResult(status="invalid_input", error_code="bad_args",
                          observation="query must be a non-empty string")
    max_results = args.get("max_results", 10)
    if not isinstance(max_results, int) or max_results <= 0:
        max_results = 10
    max_results = min(max_results, MAX_SEARCH_RESULTS)
    max_snippet_length = args.get("max_snippet_length", 500)
    if not isinstance(max_snippet_length, int) or max_snippet_length <= 0:
        max_snippet_length = 500
    max_snippet_length = min(max_snippet_length, MAX_SNIPPET_LENGTH)
    try:
        result = await _doubao_search(query.strip(), max_results, max_snippet_length)
    except DoubaoSearchError as e:
        return ToolResult(status="error", error_code="search_failed", observation=str(e))
    if not result:
        return ToolResult(status="error", error_code="search_failed",
                          observation="豆包搜索未返回结果")
    return ToolResult(status="ok", observation=result)


DOUBAO_SEARCH_SPEC = ToolSpec(
    name="doubao_search",
    description="豆包搜索（Global 版）联网搜索，返回标题、链接、来源站点、发布时间与正文摘要；"
                "适合中文互联网最新信息检索，与 web_search 可互为补充",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "minLength": 1,
                "description": "搜索关键词，1~100 字符，使用主体、主题等具体词组，不要照抄整句问题",
            },
            "max_results": {
                "type": "integer", "minimum": 1, "maximum": 20, "default": 10,
                "description": "最大返回结果数",
            },
            "max_snippet_length": {
                "type": "integer", "minimum": 1, "maximum": 3000, "default": 500,
                "description": "单个摘要片段的最大 token 数，推荐 1000 以内",
            },
        },
        "required": ["query"],
        "additionalProperties": False,
    },
    handler=doubao_search,
)
