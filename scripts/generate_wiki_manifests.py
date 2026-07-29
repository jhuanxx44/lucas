#!/usr/bin/env python3
"""为受控干扰与自然增长轨道生成嵌套 Wiki 子库 manifest。"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


DEFAULT_CORPUS = ROOT / "evals/corpora/wiki-scale-v1"
SIZES = (50, 100, 200, 500)
SEEDS = (1, 2, 3, 4, 5)


@lru_cache(maxsize=None)
def _metadata(master: Path, path: str) -> tuple[str, int]:
    text = (master / path).read_text(encoding="utf-8")
    parts = text.split("---", 2)
    frontmatter = yaml.safe_load(parts[1]) if len(parts) == 3 else {}
    return frontmatter.get("industry", "unknown"), len(text)


def stratified_order(paths: list[str], master: Path, salt: str) -> list[str]:
    lengths = sorted(_metadata(master, path)[1] for path in paths)
    cuts = [lengths[int((len(lengths) - 1) * fraction)] for fraction in (0.25, 0.5, 0.75)] if lengths else []
    buckets: dict[tuple[str, int], list[str]] = defaultdict(list)
    for path in paths:
        domain, length = _metadata(master, path)
        quartile = sum(length > cut for cut in cuts)
        buckets[(domain, quartile)].append(path)
    for key, values in buckets.items():
        values.sort(key=lambda path: hashlib.sha256(f"{salt}:{key}:{path}".encode()).hexdigest())
    keys = sorted(buckets, key=lambda key: hashlib.sha256(f"{salt}:{key}".encode()).hexdigest())
    ordered = []
    while len(ordered) < len(paths):
        for key in keys:
            if buckets[key]:
                ordered.append(buckets[key].pop(0))
    return ordered


def _write_manifest(path: Path, payload: dict) -> None:
    documents = payload["documents"]
    payload = {
        **payload,
        "documents_sha256": hashlib.sha256("\n".join(sorted(documents)).encode()).hexdigest(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def generate_manifests(corpus_root: Path) -> dict:
    master = corpus_root / "master/wiki"
    all_paths = sorted(path.relative_to(master).as_posix() for path in master.rglob("*.md") if path.name != "index.md")
    queries = json.loads((corpus_root / "queries/all.json").read_text(encoding="utf-8"))["queries"]
    version = json.loads((corpus_root / "VERSION.json").read_text(encoding="utf-8"))
    root = corpus_root / "manifests"
    for query in queries:
        gt = list(dict.fromkeys(query["ground_truth"]))
        if len(gt) > min(SIZES):
            raise ValueError(f"{query['id']} ground truth does not fit smallest subset")
        distractors = [path for path in all_paths if path not in set(gt)]
        for seed in SEEDS:
            order = stratified_order(distractors, master, f"controlled:{query['id']}:{seed}")
            for size in SIZES:
                docs = sorted(gt + order[:size - len(gt)])
                _write_manifest(
                    root / f"controlled/{query['id']}/seed-{seed}/n{size:04d}.json",
                    {
                        "corpus_version": version["version"], "corpus_sha256": version["corpus_sha256"],
                        "track": "controlled", "query_id": query["id"], "seed": seed,
                        "size": size, "ground_truth": gt, "documents": docs,
                    },
                )
    for seed in SEEDS:
        order = stratified_order(all_paths, master, f"natural:{seed}")
        for size in SIZES:
            docs = sorted(order[:size])
            _write_manifest(
                root / f"natural/seed-{seed}/n{size:04d}.json",
                {
                    "corpus_version": version["version"], "corpus_sha256": version["corpus_sha256"],
                    "track": "natural", "seed": seed, "size": size, "documents": docs,
                },
            )
    return {"controlled": len(queries) * len(SEEDS) * len(SIZES), "natural": len(SEEDS) * len(SIZES)}


def validate_manifests(corpus_root: Path) -> dict:
    root = corpus_root / "manifests"
    errors = []
    files = sorted(root.rglob("*.json"))
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for path in files:
        row = json.loads(path.read_text(encoding="utf-8"))
        docs = row.get("documents", [])
        if len(docs) != row.get("size") or len(docs) != len(set(docs)):
            errors.append(f"invalid size or duplicates: {path}")
        digest = hashlib.sha256("\n".join(sorted(docs)).encode()).hexdigest()
        if digest != row.get("documents_sha256"):
            errors.append(f"hash mismatch: {path}")
        if row.get("track") == "controlled" and not set(row.get("ground_truth", [])) <= set(docs):
            errors.append(f"missing ground truth: {path}")
        groups[(row.get("track"), row.get("query_id"), row.get("seed"))].append(row)
    for key, rows in groups.items():
        rows.sort(key=lambda row: row["size"])
        if [row["size"] for row in rows] != list(SIZES):
            errors.append(f"wrong sizes: {key}")
        for smaller, larger in zip(rows, rows[1:]):
            if not set(smaller["documents"]) < set(larger["documents"]):
                errors.append(f"not strictly nested: {key} {smaller['size']}->{larger['size']}")
    report = {"passed": not errors, "manifest_count": len(files), "group_count": len(groups), "errors": errors}
    (corpus_root / "quality/manifest-validation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus-root", type=Path, default=DEFAULT_CORPUS)
    args = parser.parse_args()
    counts = generate_manifests(args.corpus_root)
    report = validate_manifests(args.corpus_root)
    print(json.dumps({**counts, **report}, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
