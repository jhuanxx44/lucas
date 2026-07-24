"""Lucas 本地 Wiki 知识召回工具。"""
from pathlib import Path

from harness.tools.base import ToolResult, ToolSpec
from utils.path_safety import resolve_within
from utils.wiki_core import recall_wiki

RECALL_PAGE_CHARS = 3000


def wiki_recall(workspace: Path, args: dict) -> ToolResult:
    query = args.get("query")
    if not isinstance(query, str) or not query.strip():
        return ToolResult(status="invalid_input", error_code="bad_args",
                          observation="query must be a non-empty string")
    workspace_root = workspace.resolve()
    wiki_candidate = workspace_root / "wiki"
    if not wiki_candidate.exists() and not wiki_candidate.is_symlink():
        return ToolResult(status="ok", observation="（wiki 知识库为空，没有可召回的页面）")
    wiki_root = resolve_within(workspace_root, wiki_candidate, strict=True)
    if wiki_root is None or not wiki_root.is_dir():
        return ToolResult(status="denied", error_code="path_escape",
                          observation="wiki root escapes workspace")
    try:
        pages = recall_wiki(str(wiki_root), query.strip(), max_chars=RECALL_PAGE_CHARS)
    except Exception as e:
        return ToolResult(status="error", error_code="recall_failed",
                          observation=f"{type(e).__name__}: {e}")
    if not pages:
        return ToolResult(status="ok",
                          observation=f"知识库中没有与「{query.strip()}」相关的页面")
    parts = []
    for page in pages:
        header = f"--- {page['name']}（{page['path']}） ---"
        body = page["content"] + ("\n…[truncated]" if page["truncated"] else "")
        parts.append(f"{header}\n{body}")
    return ToolResult(status="ok", observation="\n\n".join(parts))


WIKI_RECALL_SPEC = ToolSpec(
    name="wiki_recall",
    description="从本地 wiki 知识库召回相关页面：先按索引（index.md）条目匹配，不足再全文检索；返回页面正文（每页最多 3000 字符）",
    args_description='{"query": "检索关键词，如公司名、行业、主题"}',
    handler=wiki_recall,
)
