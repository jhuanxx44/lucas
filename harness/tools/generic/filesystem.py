import re
from pathlib import Path

import yaml

from harness.tools.base import ToolResult, ToolSpec
from utils.path_safety import resolve_within


def _resolve_in_workspace(workspace: Path, relative: str) -> Path | None:
    """解析工作区内路径；越界（..、绝对路径、symlink 逃逸）返回 None"""
    if not isinstance(relative, str) or not relative:
        return None
    candidate = Path(relative)
    if candidate.is_absolute():
        return None
    return resolve_within(workspace, workspace / candidate, strict=False)


def read_file(workspace: Path, args: dict) -> ToolResult:
    path = _resolve_in_workspace(workspace, args.get("path"))
    if path is None:
        return ToolResult(status="denied", error_code="path_escape",
                          observation="path escapes workspace")
    if not path.is_file():
        return ToolResult(status="error", error_code="not_found",
                          observation=f"file not found: {args.get('path')}")
    max_chars = args.get("max_chars", 16000)
    if not isinstance(max_chars, int) or max_chars <= 0:
        max_chars = 16000
    offset = args.get("offset", 0)
    if not isinstance(offset, int) or offset < 0:
        offset = 0
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        return ToolResult(status="error", error_code="read_failed", observation=str(e))
    if offset >= len(content):
        return ToolResult(
            status="ok",
            observation=f"offset {offset} beyond end of file (total {len(content)} chars)",
            truncated=False,
        )
    sliced = content[offset:offset + max_chars]
    truncated = (offset + len(sliced)) < len(content)
    if truncated:
        header = f"[chars {offset}-{offset + len(sliced)} of {len(content)}, truncated]\n"
    else:
        header = f"[chars {offset}-{offset + len(sliced)} of {len(content)}]\n"
    return ToolResult(
        status="ok",
        observation=header + sliced,
        truncated=truncated,
    )


def apply_patch(workspace: Path, args: dict) -> ToolResult:
    path = _resolve_in_workspace(workspace, args.get("path"))
    if path is None:
        return ToolResult(status="denied", error_code="path_escape",
                          observation="path escapes workspace")
    old, new = args.get("old"), args.get("new")
    if not isinstance(old, str) or not isinstance(new, str) or not old:
        return ToolResult(status="invalid_input", error_code="bad_args",
                          observation="old and new must be non-empty strings")
    if not path.is_file():
        return ToolResult(status="error", error_code="not_found",
                          observation=f"file not found: {args.get('path')}")
    content = path.read_text(encoding="utf-8")
    occurrences = content.count(old)
    if occurrences == 0:
        return ToolResult(
            status="invalid_input", error_code="old_not_unique",
            observation="old occurs 0 times, must occur exactly once",
        )
    if occurrences > 1:
        lines = [f"old occurs {occurrences} times, must occur exactly once. 出现位置:"]
        pos = 0
        for _ in range(min(occurrences, 5)):
            idx = content.find(old, pos)
            line_start = content.rfind("\n", 0, idx) + 1
            line_end = content.find("\n", idx)
            if line_end == -1:
                line_end = len(content)
            lines.append(f"[chars {idx}] ...{content[line_start:line_end].strip()}...")
            pos = idx + len(old)
        if occurrences > 5:
            lines.append(f"... 以及另外 {occurrences - 5} 处")
        return ToolResult(
            status="invalid_input", error_code="old_not_unique",
            observation="\n".join(lines),
        )
    path.write_text(content.replace(old, new, 1), encoding="utf-8")
    return ToolResult(status="ok", observation=f"patched {args.get('path')}")


_WIKI_SUMMARY_ERROR = (
    "wiki 页面必须在 frontmatter 中包含 summary 字段（2-4 句中文 TL;DR）。\n"
    "示例 frontmatter：\n"
    "---\n"
    "title: 页面标题\n"
    "type: company\n"
    "summary: '2-4 句中文摘要，概括核心信息、关键数据和时间范围'\n"
    "---"
)


def _has_summary_frontmatter(content: str) -> bool:
    if not content.startswith("---"):
        return False
    parts = content.split("---", 2)
    if len(parts) < 3:
        return False
    try:
        fm = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return False
    return bool(fm.get("summary", "").strip())


def write_file(workspace: Path, args: dict) -> ToolResult:
    path = _resolve_in_workspace(workspace, args.get("path"))
    if path is None:
        return ToolResult(status="denied", error_code="path_escape",
                          observation="path escapes workspace")
    content = args.get("content")
    if not isinstance(content, str):
        return ToolResult(status="invalid_input", error_code="bad_args",
                          observation="content must be a string")
    # wiki 写入校验：.md 文件必须包含 non-empty summary frontmatter
    # 排除 index.md / glossary.md（索引和术语表不需要 summary）
    ws_root = workspace.resolve()
    rel_to_ws = str(path.resolve().relative_to(ws_root))
    if (rel_to_ws.startswith("wiki/") and path.suffix == ".md"
            and path.name not in ("index.md", "glossary.md")):
        if not _has_summary_frontmatter(content):
            return ToolResult(
                status="invalid_input", error_code="missing_summary",
                observation=_WIKI_SUMMARY_ERROR,
            )

    if path.exists():
        if args.get("overwrite") is not True:
            return ToolResult(
                status="denied", error_code="already_exists",
                observation=f"file already exists: {args.get('path')}（如需覆盖请传 overwrite: true）",
            )
        if not path.is_file():
            return ToolResult(status="invalid_input", error_code="not_a_file",
                              observation=f"not a file: {args.get('path')}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return ToolResult(status="ok", observation=f"wrote {args.get('path')} ({len(content)} chars)")


LIST_FILES_MAX_ENTRIES = 200


def _format_size(size: int) -> str:
    if size < 1024:
        return f"{size}B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f}KB"
    return f"{size / (1024 * 1024):.1f}MB"


def list_files(workspace: Path, args: dict) -> ToolResult:
    raw_path = args.get("path")
    if raw_path in (None, ""):
        target = workspace.resolve()
    else:
        target = _resolve_in_workspace(workspace, raw_path)
        if target is None:
            return ToolResult(status="denied", error_code="path_escape",
                              observation="path escapes workspace")
    if not target.is_dir():
        return ToolResult(status="error", error_code="not_found",
                          observation=f"directory not found: {raw_path or '.'}")
    max_depth = args.get("max_depth", 2)
    if not isinstance(max_depth, int) or max_depth <= 0:
        max_depth = 2

    lines: list[str] = [f"📁 {target.name or '.'}/"]
    count = 0
    truncated_listing = False

    def walk(directory: Path, depth: int) -> None:
        """列出 directory 的直接子项；depth 为子项所在层级（从 1 开始）"""
        nonlocal count, truncated_listing
        try:
            def sort_key(path: Path) -> tuple[int, str]:
                if path.is_symlink():
                    return 2, path.name
                return (0 if path.is_dir() else 1), path.name

            children = sorted(directory.iterdir(), key=sort_key)
        except OSError:
            return
        for child in children:
            if count >= LIST_FILES_MAX_ENTRIES:
                truncated_listing = True
                return
            count += 1
            indent = "  " * depth
            if child.is_symlink():
                lines.append(f"{indent}🔗 {child.name}（已跳过 symlink）")
                continue
            if child.is_dir():
                try:
                    n = sum(1 for _ in child.iterdir())
                except OSError:
                    n = 0
                lines.append(f"{indent}📁 {child.name}/ ({n} 项)")
                if depth < max_depth:
                    walk(child, depth + 1)
            else:
                try:
                    size = child.stat().st_size
                except OSError:
                    size = 0
                lines.append(f"{indent}📄 {child.name} ({_format_size(size)})")

    walk(target, 1)
    if truncated_listing:
        lines.append(f"... 条目超过 {LIST_FILES_MAX_ENTRIES}，已截断")
    return ToolResult(status="ok", observation="\n".join(lines))


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
        candidates = sorted(root.rglob("*"))

    ws_root = workspace.resolve()
    hits: list[tuple[str, int, str]] = []  # (相对路径, 字符偏移, 上下文)
    skipped: list[str] = []
    truncated_total = False

    for path in candidates:
        if len(hits) >= MAX_TOTAL_RESULTS:
            truncated_total = True
            break
        if path.is_symlink():
            continue
        safe_path = resolve_within(ws_root, path, strict=True)
        if safe_path is None or not safe_path.is_file():
            continue
        try:
            if safe_path.stat().st_size > MAX_FILE_BYTES:
                skipped.append(str(safe_path.relative_to(ws_root)))
                continue
            content = safe_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError, ValueError):
            continue
        lines = content.split("\n")
        offsets = []
        pos = 0
        for line in lines:
            offsets.append(pos)
            pos += len(line) + 1
        for index, line in enumerate(lines):
            if len(hits) >= MAX_TOTAL_RESULTS:
                truncated_total = True
                break
            if not is_match(line):
                continue
            context_start = max(0, index - 1)
            context_end = min(len(lines), index + 2)
            snippet = "\n".join(lines[context_start:context_end])
            rel = str(safe_path.relative_to(ws_root))
            hits.append((rel, offsets[index], snippet))
        if truncated_total:
            break

    hits.sort(key=lambda hit: (hit[0], hit[1]))
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


READ_FILE_SPEC = ToolSpec(
    name="read_file",
    description="读取工作区内文件内容（只读）",
    args_description='{"path": "相对工作区的文件路径", "max_chars": 可选，最大返回字符数，默认 16000", "offset": 可选，起始字符偏移量，默认 0}',
    handler=read_file,
)

APPLY_PATCH_SPEC = ToolSpec(
    name="apply_patch",
    description="对工作区内文件做精确字符串替换（old 必须在文件中唯一出现）",
    args_description='{"path": "相对工作区的文件路径", "old": "被替换的原文", "new": "替换后的内容"}',
    handler=apply_patch,
)

LIST_FILES_SPEC = ToolSpec(
    name="list_files",
    description="列出工作区内目录结构（含文件大小，只读）",
    args_description='{"path": "可选，相对工作区的子目录，默认工作区根", "max_depth": 可选，展开深度，默认 2}',
    handler=list_files,
)

WRITE_FILE_SPEC = ToolSpec(
    name="write_file",
    description="在工作区内新建文件并整体写入内容；文件已存在时默认拒绝，需 overwrite: true 才覆盖",
    args_description='{"path": "相对工作区的文件路径", "content": "完整文件内容", "overwrite": 可选，传 true 才允许覆盖已存在文件}',
    handler=write_file,
)

SEARCH_SPEC = ToolSpec(
    name="search",
    description="在工作区内搜索文本（默认字面匹配；query 以 re: 开头时按正则处理）",
    args_description='{"query": "搜索字符串，re: 前缀表示正则", "path": "可选，相对工作区的子目录或文件，默认整个工作区", "max_results": 可选，默认 10}',
    handler=search,
)
