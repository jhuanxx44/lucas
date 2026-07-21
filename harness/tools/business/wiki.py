"""Lucas 本地 Wiki 知识召回工具。"""
from pathlib import Path

from harness.tools.base import ToolResult, ToolSpec
from utils.path_safety import resolve_within
from utils.wiki_core import recall_wiki

MAX_RECALL_LIMIT = 5


def wiki_recall(workspace: Path, args: dict) -> ToolResult:
    query = args.get("query")
    if not isinstance(query, str) or not query.strip():
        return ToolResult(status="invalid_input", error_code="bad_args",
                          observation="query must be a non-empty string")
    limit = args.get("limit", 3)
    if not isinstance(limit, int) or limit <= 0:
        limit = 3
    limit = min(limit, MAX_RECALL_LIMIT)
    workspace_root = workspace.resolve()
    wiki_candidate = workspace_root / "wiki"
    if not wiki_candidate.exists() and not wiki_candidate.is_symlink():
        return ToolResult(status="ok", observation="（wiki 知识库为空，没有可召回的页面）")
    wiki_root = resolve_within(workspace_root, wiki_candidate, strict=True)
    if wiki_root is None or not wiki_root.is_dir():
        return ToolResult(status="denied", error_code="path_escape",
                          observation="wiki root escapes workspace")
    try:
        pages = recall_wiki(str(wiki_root), query.strip(), limit=limit)
    except Exception as e:
        return ToolResult(status="error", error_code="recall_failed",
                          observation=f"{type(e).__name__}: {e}")
    if not pages:
        return ToolResult(status="ok",
                          observation=f"知识库中没有与「{query.strip()}」相关的页面")
    # 只返回定位信息（路径 + 摘要），正文交给 read_file 按需读取。
    # 路径加 wiki/ 前缀：recall 内部相对 wiki 根，read_file 相对工作区根，需对齐。
    lines = [f"找到 {len(pages)} 个相关页面（用 read_file 读取具体路径查看正文）："]
    for page in pages:
        read_path = f"wiki/{page['path']}"
        summary = page.get("summary") or "（无摘要）"
        lines.append(f"- {read_path} — {page['name']}：{summary}")
    return ToolResult(status="ok", observation="\n".join(lines))


WIKI_RECALL_SPEC = ToolSpec(
    name="wiki_recall",
    description="从本地 wiki 知识库召回相关页面：先按索引（index.md）条目匹配，不足再全文检索。"
                "只返回相关文件的路径和一句话摘要，不含正文；需要正文时用 read_file 读取返回的路径。"
                "没有相关页面时会明确告知。",
    args_description='{"query": "检索关键词，如公司名、行业、主题", "limit": "可选，返回页面数，默认 3，上限 5"}',
    handler=wiki_recall,
)
