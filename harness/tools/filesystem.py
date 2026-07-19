from pathlib import Path

from harness.tools.base import ToolResult, ToolSpec


def _resolve_in_workspace(workspace: Path, relative: str) -> Path | None:
    """解析工作区内路径；越界（..、绝对路径、symlink 逃逸）返回 None"""
    if not isinstance(relative, str) or not relative:
        return None
    candidate = Path(relative)
    if candidate.is_absolute():
        return None
    try:
        resolved = (workspace / candidate).resolve()
    except OSError:
        return None
    root = workspace.resolve()
    if resolved != root and root not in resolved.parents:
        return None
    return resolved


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


def write_file(workspace: Path, args: dict) -> ToolResult:
    path = _resolve_in_workspace(workspace, args.get("path"))
    if path is None:
        return ToolResult(status="denied", error_code="path_escape",
                          observation="path escapes workspace")
    content = args.get("content")
    if not isinstance(content, str):
        return ToolResult(status="invalid_input", error_code="bad_args",
                          observation="content must be a string")
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
            children = sorted(directory.iterdir(), key=lambda p: (not p.is_dir(), p.name))
        except OSError:
            return
        for child in children:
            if count >= LIST_FILES_MAX_ENTRIES:
                truncated_listing = True
                return
            count += 1
            indent = "  " * depth
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
