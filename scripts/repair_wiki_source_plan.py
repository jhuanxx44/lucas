#!/usr/bin/env python3
"""用已策展储备候选替换抓取失败和内容重定向重复的来源。"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.discover_wiki_sources import group_for_domain, title_key
from scripts.wiki_corpus_common import load_jsonl, validate_source_plan


DEFAULT_CORPUS = ROOT / "evals/corpora/wiki-scale-v1"


def repair_plan(corpus_root: Path, plan_path: Path, output_path: Path,
                compile_results_path: Path | None = None,
                report_path: Path | None = None) -> dict:
    plan = load_jsonl(plan_path)
    plan_by_doc = {entry["doc_id"]: entry for entry in plan}
    order = {entry["doc_id"]: index for index, entry in enumerate(plan)}
    pilot_ids = {entry["doc_id"] for entry in load_jsonl(corpus_root / "source-plan.jsonl")}
    catalog = load_jsonl(corpus_root / "sources/catalog.jsonl")
    records_by_doc: dict[str, list[dict]] = defaultdict(list)
    for record in catalog:
        records_by_doc[record["doc_id"]].append(record)

    removed: dict[str, str] = {}
    for entry in plan:
        records = records_by_doc.get(entry["doc_id"], [])
        if len(records) != len(entry["urls"]) or any(record.get("status") != "ok" for record in records):
            removed[entry["doc_id"]] = "source_fetch_failed"

    if compile_results_path is not None:
        for result in load_jsonl(compile_results_path):
            if result.get("status") in ("compile_failed", "missing_snapshot"):
                removed[result["doc_id"]] = result["status"]

    hashes: dict[str, list[str]] = defaultdict(list)
    for record in catalog:
        if record.get("status") == "ok" and record.get("content_sha256"):
            hashes[record["content_sha256"]].append(record["doc_id"])
    duplicate_groups = []
    for doc_ids in hashes.values():
        unique = sorted(set(doc_ids), key=lambda doc_id: (
            0 if doc_id in pilot_ids else 1,
            order.get(doc_id, 10**9),
        ))
        if len(unique) <= 1:
            continue
        keep = unique[0]
        duplicate_groups.append({"keep": keep, "remove": unique[1:]})
        for doc_id in unique[1:]:
            removed[doc_id] = f"duplicate_content_of:{keep}"

    kept = [entry for entry in plan if entry["doc_id"] not in removed]
    targets = {"target": 150, "near": 200, "far": 150}
    counts = Counter(group_for_domain(entry["domain"]) for entry in kept)
    deficits = {group: target - counts[group] for group, target in targets.items()}

    used_urls = {url for entry in kept for url in entry["urls"]}
    used_titles = {title_key(Path(entry["target_path"]).stem) for entry in kept}
    previously_selected_ids = set(plan_by_doc)
    # 历次淘汰是永久 rejection ledger；catalog 会随新计划清理，不能因此忘记旧失败。
    for old_report_path in (corpus_root / "quality").glob("source-plan*repair.json"):
        try:
            old_report = json.loads(old_report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        previously_selected_ids.update((old_report.get("removed") or {}).keys())
    classifications = load_jsonl(corpus_root / "quality/candidate-classifications.jsonl")
    reserves: dict[str, list[dict]] = defaultdict(list)
    for item in classifications:
        if (not item.get("keep") or item["doc_id"] in previously_selected_ids
                or item["url"] in used_urls):
            continue
        if title_key(item["title"]) in used_titles:
            continue
        reserves[group_for_domain(item["domain"])].append(item)
    for items in reserves.values():
        items.sort(key=lambda item: (
            -len(item.get("seed_doc_ids", [])),
            hashlib.sha256(f"repair:{item['domain']}:{item['title']}".encode()).hexdigest(),
        ))

    replacements = []
    for group in ("target", "near", "far"):
        chosen = 0
        for item in reserves[group]:
            if chosen == deficits[group]:
                break
            key = title_key(item["title"])
            if item["url"] in used_urls or key in used_titles:
                continue
            prefix = "companies" if item["page_type"] == "company" else "concepts"
            replacements.append({
                "doc_id": item["doc_id"],
                "target_path": f"{prefix}/{item['domain']}/{item['title'].replace('/', '／')}.md",
                "domain": item["domain"],
                "page_type": item["page_type"],
                "source_tier": 2,
                "urls": [item["url"]],
                "reason": item["reason"],
                "discovery": {
                    "method": "pilot-body-link+llm-curation+quality-replacement",
                    "seed_doc_ids": item.get("seed_doc_ids", []),
                },
            })
            used_urls.add(item["url"])
            used_titles.add(key)
            chosen += 1
        if chosen != deficits[group]:
            raise ValueError(f"not enough {group} reserves: need {deficits[group]}, selected {chosen}")

    repaired = kept + replacements
    errors = validate_source_plan(repaired)
    if len(repaired) != 500:
        errors.append(f"repaired plan has {len(repaired)} entries instead of 500")
    final_counts = Counter(group_for_domain(entry["domain"]) for entry in repaired)
    if final_counts != Counter(targets):
        errors.append(f"group counts changed: {dict(final_counts)}")
    if errors:
        raise ValueError("repaired plan invalid:\n" + "\n".join(errors[:20]))
    output_path.write_text(
        "".join(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n" for entry in repaired),
        encoding="utf-8",
    )
    report = {
        "removed_count": len(removed),
        "removed": removed,
        "duplicate_groups": duplicate_groups,
        "deficits": deficits,
        "replacement_doc_ids": [entry["doc_id"] for entry in replacements],
        "final_group_counts": dict(final_counts),
        "output": output_path.as_posix(),
    }
    report_path = report_path or (corpus_root / "quality/source-plan-repair.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus-root", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--plan", type=Path, default=DEFAULT_CORPUS / "source-plan-500.jsonl")
    parser.add_argument("--output", type=Path, default=DEFAULT_CORPUS / "source-plan-500-repaired.jsonl")
    parser.add_argument("--compile-results", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    print(json.dumps(
        repair_plan(args.corpus_root, args.plan, args.output, args.compile_results, args.report),
        ensure_ascii=False, indent=2,
    ))


if __name__ == "__main__":
    main()
