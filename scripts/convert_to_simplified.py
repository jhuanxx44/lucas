#!/usr/bin/env python3
"""将派生 Wiki Markdown 内容确定性地从繁体转换为简体。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from opencc import OpenCC


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WIKI_ROOT = ROOT / "evals/corpora/wiki-scale-v1/master/wiki"
RAW_ROOT = ROOT / "raw"
_CONVERTER = OpenCC("t2s")


def convert_text(text: str) -> str:
    """使用 OpenCC 的词组级 t2s 规则转换文本。"""
    current = text
    for _ in range(10):
        converted = _CONVERTER.convert(current)
        if converted == current:
            return converted
        current = converted
    raise RuntimeError("OpenCC t2s conversion did not reach a fixed point")


def _write_atomic(path: Path, text: str) -> None:
    temporary = path.with_name(f".{path.name}.simplified.part")
    try:
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def convert_tree(wiki_root: Path, apply: bool = False,
                 raw_root: Path = RAW_ROOT) -> dict:
    """扫描目录中的所有 Markdown；默认仅报告，传入 apply 才写回内容。

    文件名是 manifest 和 judgment 使用的稳定文档 ID，因此不会被重命名。
    """
    wiki_root = wiki_root.resolve()
    raw_root = raw_root.resolve()
    if wiki_root.is_relative_to(raw_root):
        raise ValueError(f"refusing to convert immutable raw input: {wiki_root}")
    if not wiki_root.is_dir():
        raise ValueError(f"wiki root is not a directory: {wiki_root}")

    scanned = 0
    changed = []
    for path in sorted(
        path for path in wiki_root.rglob("*.md") if path.name != "index.md"
    ):
        scanned += 1
        original = path.read_text(encoding="utf-8")
        converted = convert_text(original)
        if converted == original:
            continue
        changed.append(path.relative_to(wiki_root).as_posix())
        if apply:
            _write_atomic(path, converted)
    return {
        "root": str(wiki_root),
        "mode": "apply" if apply else "dry-run",
        "scanned_files": scanned,
        "changed_files": len(changed),
        "changed_paths": changed,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=DEFAULT_WIKI_ROOT)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    result = convert_tree(args.root, apply=args.apply)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
