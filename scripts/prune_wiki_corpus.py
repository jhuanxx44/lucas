#!/usr/bin/env python3
"""报告或删除不属于权威 source plan 的流水线生成 Wiki 页面。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.wiki_corpus_common import load_jsonl, write_wiki_index


DEFAULT_CORPUS = ROOT / "evals/corpora/wiki-scale-v1"


def prune_corpus(corpus_root: Path, plan_path: Path, apply: bool = False) -> dict:
    master = corpus_root / "master/wiki"
    expected = {entry["target_path"] for entry in load_jsonl(plan_path)}
    actual = {
        path.relative_to(master).as_posix()
        for path in master.rglob("*.md") if path.name != "index.md"
    }
    unexpected = sorted(actual - expected)
    missing = sorted(expected - actual)
    removed = []
    if apply:
        for relative in unexpected:
            path = master / relative
            if path.is_symlink() or not path.is_file() or path.suffix != ".md":
                raise ValueError(f"refusing to remove unsafe path: {relative}")
            path.unlink()
            removed.append(relative)
        for directory in sorted(
            (path for path in master.rglob("*") if path.is_dir()),
            key=lambda path: len(path.parts), reverse=True,
        ):
            if directory != master and not any(directory.iterdir()):
                directory.rmdir()
        write_wiki_index(master, expected - set(missing))
    report = {
        "applied": apply,
        "expected_pages": len(expected),
        "actual_pages_before": len(actual),
        "unexpected_pages": unexpected,
        "missing_pages": missing,
        "removed_pages": removed,
    }
    quality = corpus_root / "quality"
    quality.mkdir(parents=True, exist_ok=True)
    (quality / "prune-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus-root", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    report = prune_corpus(args.corpus_root, args.plan, args.apply)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(1 if report["missing_pages"] else 0)


if __name__ == "__main__":
    main()
