import re
from pathlib import Path

from harness.tools.base import ToolResult, ToolSpec
from harness.tools.filesystem import _resolve_in_workspace

MAX_FILE_BYTES = 2 * 1024 * 1024  # 单文件超过 2MB 跳过
MAX_TOTAL_RESULTS = 50            # 全部文件合计命中上限


def search(workspace: Path, args: dict) -> ToolResult:
    query = args.get("query")
    if not isinstance(query, str) or not query:
        return ToolResult(status="invalid_input", error_code="bad_args",
                          observation="query must be a non-empty string")
    raw_path = args.get("path")
    if raw_path in (None, ""):
        root = workspace.resolve()
    else:
        root = _resolve_in_workspace(workspace, raw_path)
        if root is None:
            return ToolResult(status="denied", error_code="path_escape",
                              observation="path escapes workspace")
        if not root.exists():
            return ToolResult(status="error", error_code="not_found",
                              observation=f"path not found: {raw_path}")
    max_results = args.get("max_results", 10)
    if not isinstance(max_results, int) or max_results <= 0:
        max_results = 10

    # 默认字面搜索；仅 re: 前缀且正则合法时按正则处理，否则回退字面
    regex = None
    if query.startswith("re:"):
        try:
            regex = re.compile(query[3:])
        except re.error:
            regex = None
    if regex is not None:
        is_match = regex.search
    else:
        def is_match(line: str, _needle=query) -> bool:
            return _needle in line

    if root.is_file():
        candidates = [root]
    else:
        candidates = sorted(p for p in root.rglob("*") if p.is_file())

    ws_root = workspace.resolve()
    hits: list[tuple[str, int, str]] = []  # (相对路径, 字符偏移, 上下文)
    skipped: list[str] = []
    truncated_total = False

    for path in candidates:
        if len(hits) >= MAX_TOTAL_RESULTS:
            truncated_total = True
            break
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                skipped.append(str(path.relative_to(ws_root)))
                continue
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError, ValueError):
            continue
        lines = content.split("\n")
        offsets = []
        pos = 0
        for line in lines:
            offsets.append(pos)
            pos += len(line) + 1
        for i, line in enumerate(lines):
            if len(hits) >= MAX_TOTAL_RESULTS:
                truncated_total = True
                break
            if not is_match(line):
                continue
            context_start = max(0, i - 1)
            context_end = min(len(lines), i + 2)
            snippet = "\n".join(lines[context_start:context_end])
            rel = str(path.relative_to(ws_root))
            hits.append((rel, offsets[i], snippet))
        if truncated_total:
            break

    hits.sort(key=lambda h: (h[0], h[1]))
    shown = hits[:max_results]
    header = f"找到 {len(hits)} 处匹配:"
    body = [f"{rel} [chars {offset}] {snippet}" for rel, offset, snippet in shown]
    lines_out = [header, *body]
    if len(hits) > max_results:
        lines_out.append(f"... 仅显示前 {max_results} 处（共 {len(hits)} 处）")
    if truncated_total:
        lines_out.append(f"... 结果达到上限 {MAX_TOTAL_RESULTS}，可能还有更多匹配")
    if skipped:
        lines_out.append(f"已跳过超过 2MB 的文件: {', '.join(skipped)}")
    return ToolResult(status="ok", observation="\n".join(lines_out))


SEARCH_SPEC = ToolSpec(
    name="search",
    description="在工作区内搜索文本（默认字面匹配；query 以 re: 开头时按正则处理）",
    args_description='{"query": "搜索字符串，re: 前缀表示正则", "path": "可选，相对工作区的子目录或文件，默认整个工作区", "max_results": 可选，默认 10}',
    handler=search,
)
