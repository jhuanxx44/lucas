#!/usr/bin/env python3
"""对 Wiki 规模实验母库执行确定性质量门禁并生成版本证据。"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
import sys
from collections import Counter
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.wiki_corpus_common import (
    load_jsonl,
    validate_source_plan,
    validate_wiki_page,
    write_wiki_index,
)


DEFAULT_CORPUS = ROOT / "evals/corpora/wiki-scale-v1"


def _normalized_body(text: str) -> str:
    body = text.split("---", 2)[-1]
    body = body.split("\n## 来源", 1)[0]
    body = re.sub(r"^#+.*$", "", body, flags=re.MULTILINE)
    body = re.sub(r"\[S\d+\]", "", body)
    return re.sub(r"\s+", "", body).casefold()


def _simhash(text: str) -> int:
    if len(text) < 5:
        return 0
    vector = [0] * 64
    for index in range(len(text) - 4):
        shingle = text[index:index + 5]
        digest = int.from_bytes(hashlib.blake2b(shingle.encode(), digest_size=8).digest(), "big")
        for bit in range(64):
            vector[bit] += 1 if digest & (1 << bit) else -1
    value = 0
    for bit, weight in enumerate(vector):
        if weight >= 0:
            value |= 1 << bit
    return value


def _frontmatter(path: Path) -> dict:
    parts = path.read_text(encoding="utf-8").split("---", 2)
    return yaml.safe_load(parts[1]) if len(parts) == 3 else {}


def validate_corpus(corpus_root: Path, required_count: int | None,
                    plan_path: Path | None = None) -> dict:
    plan_path = (plan_path or corpus_root / "source-plan.jsonl").resolve()
    corpus_root = corpus_root.resolve()
    plan = load_jsonl(plan_path)
    plan_errors = validate_source_plan(plan)
    catalog = load_jsonl(corpus_root / "sources/catalog.jsonl")
    master = corpus_root / "master/wiki"
    pages = sorted(path for path in master.rglob("*.md") if path.name != "index.md")
    actual_paths = {path.relative_to(master).as_posix() for path in pages}
    expected_paths = {entry["target_path"] for entry in plan}

    errors = list(plan_errors)
    if required_count is not None and len(pages) != required_count:
        errors.append(f"expected {required_count} pages, found {len(pages)}")
    missing_pages = sorted(expected_paths - actual_paths)
    unexpected_pages = sorted(actual_paths - expected_paths)
    if missing_pages:
        errors.append(f"missing planned pages: {missing_pages}")
    if unexpected_pages:
        errors.append(f"unexpected pages: {unexpected_pages}")

    records_by_doc: dict[str, list[dict]] = {}
    for record in catalog:
        records_by_doc.setdefault(record.get("doc_id", ""), []).append(record)
        if record.get("status") != "ok":
            errors.append(f"catalog source is not usable: {record.get('doc_id')} {record.get('source_id')}")
        snapshot = corpus_root / record.get("snapshot_path", "")
        if not snapshot.is_file():
            errors.append(f"catalog snapshot missing: {record.get('snapshot_path')}")
            continue
        data = json.loads(snapshot.read_text(encoding="utf-8"))
        markdown = data.get("markdown", "")
        digest = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
        if digest != record.get("content_sha256"):
            errors.append(f"snapshot hash mismatch: {record.get('snapshot_path')}")

    plan_by_path = {entry["target_path"]: entry for entry in plan}
    page_errors = {}
    lengths = []
    domains = Counter()
    for page in pages:
        relative = page.relative_to(master).as_posix()
        source = plan_by_path.get(relative)
        allowed = {
            record["source_id"] for record in records_by_doc.get(source["doc_id"], [])
            if record.get("status") == "ok"
        } if source else set()
        current_errors = validate_wiki_page(page, allowed)
        if current_errors:
            page_errors[relative] = current_errors
            errors.extend(current_errors)
        text = page.read_text(encoding="utf-8")
        lengths.append(len(text))
        domains[_frontmatter(page).get("industry", "unknown")] += 1

    exact: dict[str, list[str]] = {}
    simhashes = {}
    for page in pages:
        relative = page.relative_to(master).as_posix()
        normalized = _normalized_body(page.read_text(encoding="utf-8"))
        digest = hashlib.sha256(normalized.encode()).hexdigest()
        exact.setdefault(digest, []).append(relative)
        simhashes[relative] = _simhash(normalized)
    exact_duplicates = [paths for paths in exact.values() if len(paths) > 1]
    near_duplicates = []
    relative_paths = sorted(simhashes)
    for index, first in enumerate(relative_paths):
        for second in relative_paths[index + 1:]:
            distance = (simhashes[first] ^ simhashes[second]).bit_count()
            if distance <= 3:
                near_duplicates.append({"first": first, "second": second, "distance": distance})

    duplicate_rate = len({p for pair in near_duplicates for p in (pair["first"], pair["second"])}) / max(len(pages), 1)
    if exact_duplicates:
        errors.append(f"exact duplicate groups found: {len(exact_duplicates)}")
    if duplicate_rate > 0.02:
        errors.append(f"near duplicate page rate exceeds 2%: {duplicate_rate:.2%}")

    source_tiers = [record.get("source_tier", 3) for record in catalog]
    tier_12_rate = sum(tier in (1, 2) for tier in source_tiers) / max(len(source_tiers), 1)
    if tier_12_rate < 0.8:
        errors.append(f"tier 1/2 source rate below 80%: {tier_12_rate:.2%}")

    write_wiki_index(master, actual_paths)
    corpus_hash = hashlib.sha256()
    for page in sorted(master.rglob("*.md")):
        corpus_hash.update(page.relative_to(master).as_posix().encode())
        corpus_hash.update(hashlib.sha256(page.read_bytes()).digest())

    duplicate_report = {
        "exact_duplicate_groups": exact_duplicates,
        "near_duplicates": near_duplicates,
        "near_duplicate_page_rate": round(duplicate_rate, 6),
    }
    quality = corpus_root / "quality"
    quality.mkdir(parents=True, exist_ok=True)
    (quality / "duplicates.json").write_text(
        json.dumps(duplicate_report, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    report = {
        "passed": not errors,
        "page_count": len(pages),
        "source_count": len(catalog),
        "tier_1_2_source_rate": round(tier_12_rate, 6),
        "schema_valid_rate": round((len(pages) - len(page_errors)) / max(len(pages), 1), 6),
        "exact_duplicate_groups": len(exact_duplicates),
        "near_duplicate_page_rate": round(duplicate_rate, 6),
        "page_chars": {
            "min": min(lengths, default=0),
            "median": round(statistics.median(lengths), 1) if lengths else 0,
            "max": max(lengths, default=0),
        },
        "domains": dict(sorted(domains.items())),
        "corpus_sha256": corpus_hash.hexdigest(),
        "errors": errors,
        "page_errors": page_errors,
    }
    (quality / "validation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    if report["passed"]:
        version = {
            "version": corpus_root.name,
            "frozen_on": date.today().isoformat(),
            "page_count": len(pages),
            "source_count": len(catalog),
            "corpus_sha256": report["corpus_sha256"],
            "source_plan_sha256": hashlib.sha256(
                plan_path.read_bytes()
            ).hexdigest(),
            "source_plan": str(plan_path.relative_to(corpus_root)),
            "catalog_sha256": hashlib.sha256(
                (corpus_root / "sources/catalog.jsonl").read_bytes()
            ).hexdigest(),
            "quality_status": "deterministic-gates-passed",
        }
        (corpus_root / "VERSION.json").write_text(
            json.dumps(version, ensure_ascii=False, indent=2), encoding="utf-8",
        )
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus-root", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--require-count", type=int)
    args = parser.parse_args()
    report = validate_corpus(args.corpus_root, args.require_count, args.plan)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
