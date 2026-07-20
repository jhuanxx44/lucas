"""共享的真实路径边界检查。"""
from pathlib import Path


def resolve_within(root: str | Path, candidate: str | Path, *, strict: bool) -> Path | None:
    """解析 symlink 后确认 candidate 仍在 root 内；失败或越界返回 None。"""
    try:
        resolved_root = Path(root).resolve(strict=True)
        resolved = Path(candidate).resolve(strict=strict)
        resolved.relative_to(resolved_root)
    except (OSError, RuntimeError, ValueError):
        return None
    return resolved
