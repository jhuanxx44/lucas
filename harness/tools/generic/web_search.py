"""公共互联网搜索工具（多供应商：Tavily / 豆包 / DuckDuckGo）。"""
from pathlib import Path

from harness.tools.base import ToolResult, ToolSpec
from utils.web_search import SEARCH_PROVIDERS, SearchProviderError, search as _web_search

MAX_SEARCH_RESULTS = 10


async def web_search(workspace: Path, args: dict) -> ToolResult:
    query = args.get("query")
    if not isinstance(query, str) or not query.strip():
        return ToolResult(status="invalid_input", error_code="bad_args",
                          observation="query must be a non-empty string")
    provider = args.get("provider", "auto")
    if not isinstance(provider, str) or provider not in SEARCH_PROVIDERS:
        return ToolResult(status="invalid_input", error_code="bad_args",
                          observation=f"provider 必须是 {list(SEARCH_PROVIDERS)} 之一")
    max_results = args.get("max_results", 5)
    if not isinstance(max_results, int) or max_results <= 0:
        max_results = 5
    max_results = min(max_results, MAX_SEARCH_RESULTS)
    try:
        result = await _web_search(query.strip(), max_results, provider)
    except SearchProviderError as e:
        return ToolResult(status="error", error_code="search_failed", observation=str(e))
    except Exception as e:
        return ToolResult(status="error", error_code="search_failed",
                          observation=f"{type(e).__name__}: {e}")
    if not result:
        observation = ("搜索未返回结果，可换关键词或更换 provider 重试"
                       if provider != "doubao" else
                       "豆包搜索未返回结果，可换关键词或改用 provider=auto 重试")
        return ToolResult(status="error", error_code="search_failed", observation=observation)
    return ToolResult(status="ok", observation=result)


WEB_SEARCH_SPEC = ToolSpec(
    name="web_search",
    description=(
        "联网搜索公开网页，返回编号、标题、链接、摘要的 markdown 列表。"
        "provider 参数指定搜索供应商（默认 auto）："
        "auto = 自动选择，优先 Tavily、失败回退 DuckDuckGo；"
        "tavily = 通用搜索，覆盖中英文及全球网页；"
        "doubao = 豆包搜索（火山引擎），中文互联网信息质量高，返回来源站点与发布时间，"
        "适合 A 股与中文财经时效性信息；"
        "duckduckgo = 免 key 传统关键词检索，兜底用。"
        "query 写法：tavily/duckduckgo 可用关键词组合或自然语言问句；"
        "doubao 优先推荐写紧凑主题短语。"
        "选择建议：中文财经或需要来源、发布时间时用 doubao；"
        "英文或海外信息用 tavily；不确定时用默认 auto。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "minLength": 1,
                "description": "搜索关键词；使用主体、主题和时间范围等具体词组，不要照抄整句问题",
            },
            "provider": {
                "type": "string",
                "enum": list(SEARCH_PROVIDERS),
                "default": "auto",
                "description": "搜索供应商：auto 自动 / tavily 通用 / doubao 中文财经 / duckduckgo 兜底",
            },
            "max_results": {
                "type": "integer", "minimum": 1, "maximum": 10, "default": 5,
                "description": "最大返回结果数",
            },
        },
        "required": ["query"],
        "additionalProperties": False,
    },
    handler=web_search,
)
