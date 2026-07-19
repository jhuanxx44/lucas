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
    max_chars = args.get("max_chars", 4000)
    if not isinstance(max_chars, int) or max_chars <= 0:
        max_chars = 4000
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        return ToolResult(status="error", error_code="read_failed", observation=str(e))
    truncated = len(content) > max_chars
    return ToolResult(
        status="ok",
        observation=content[:max_chars],
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
    if occurrences != 1:
        return ToolResult(
            status="invalid_input", error_code="old_not_unique",
            observation=f"old occurs {occurrences} times, must occur exactly once",
        )
    path.write_text(content.replace(old, new, 1), encoding="utf-8")
    return ToolResult(status="ok", observation=f"patched {args.get('path')}")


READ_FILE_SPEC = ToolSpec(
    name="read_file",
    description="读取工作区内文件内容（只读）",
    args_description='{"path": "相对工作区的文件路径", "max_chars": 可选，最大返回字符数，默认 4000}',
    handler=read_file,
)

APPLY_PATCH_SPEC = ToolSpec(
    name="apply_patch",
    description="对工作区内文件做精确字符串替换（old 必须在文件中唯一出现）",
    args_description='{"path": "相对工作区的文件路径", "old": "被替换的原文", "new": "替换后的内容"}',
    handler=apply_patch,
)
