#!/usr/bin/env python3
"""用已认证的 Firecrawl CLI 抓取 Wiki 规模实验来源并保存可追溯快照。"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.wiki_corpus_common import load_jsonl, snapshot_record, validate_source_plan


DEFAULT_CORPUS = ROOT / "evals/corpora/wiki-scale-v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_existing_catalog(path: Path) -> dict[tuple[str, str], dict]:
    if not path.is_file():
        return {}
    return {
        (entry["doc_id"], entry["source_id"]): entry
        for entry in load_jsonl(path)
        if entry.get("doc_id") and entry.get("source_id")
    }


def _scrape_one(source: dict, source_index: int, corpus_root: Path,
                existing: dict | None, force: bool) -> dict:
    source_id = f"S{source_index}"
    url = source["urls"][source_index - 1]
    source_tier = source.get("url_tiers", [source["source_tier"]] * len(source["urls"]))[
        source_index - 1
    ]
    snapshots = corpus_root / "sources/snapshots"
    snapshots.mkdir(parents=True, exist_ok=True)
    snapshot = snapshots / f"{source['doc_id']}-{source_id.lower()}.json"

    if snapshot.is_file() and not force:
        retrieved_at = (existing or {}).get("retrieved_at") or _utc_now()
        record = snapshot_record(source, snapshot, retrieved_at)
        record.update({
            "source_id": source_id,
            "source_tier": source_tier,
            "requested_url": url,
            "snapshot_path": snapshot.relative_to(corpus_root).as_posix(),
            "reused": True,
        })
        return record

    with tempfile.NamedTemporaryFile(
        prefix=f"{source['doc_id']}-", suffix=".json", dir=snapshots, delete=False
    ) as handle:
        temporary = Path(handle.name)
    command = [
        "firecrawl", "scrape", url,
        "--format", "markdown,links",
        "--only-main-content",
        "--json",
        "--output", str(temporary),
    ]
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=180, check=False,
        )
        if result.returncode != 0:
            return {
                **source,
                "source_id": source_id,
                "source_tier": source_tier,
                "requested_url": url,
                "status": "scrape_failed",
                "retrieved_at": _utc_now(),
                "error": (result.stderr or result.stdout).strip()[:1000],
            }
        data = json.loads(temporary.read_text(encoding="utf-8"))
        markdown = data.get("markdown")
        status_code = (data.get("metadata") or {}).get("statusCode")
        if not isinstance(markdown, str) or len(markdown.strip()) < 500:
            return {
                **source,
                "source_id": source_id,
                "source_tier": source_tier,
                "requested_url": url,
                "status": "content_too_short",
                "retrieved_at": _utc_now(),
                "markdown_chars": len(markdown or ""),
            }
        if isinstance(status_code, int) and status_code >= 400:
            return {
                **source,
                "source_id": source_id,
                "source_tier": source_tier,
                "requested_url": url,
                "status": "http_error",
                "retrieved_at": _utc_now(),
                "status_code": status_code,
            }
        temporary.replace(snapshot)
        record = snapshot_record(source, snapshot, _utc_now())
        record.update({
            "source_id": source_id,
            "source_tier": source_tier,
            "requested_url": url,
            "snapshot_path": snapshot.relative_to(corpus_root).as_posix(),
            "reused": False,
        })
        return record
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        return {
            **source,
            "source_id": source_id,
            "source_tier": source_tier,
            "requested_url": url,
            "status": "scrape_failed",
            "retrieved_at": _utc_now(),
            "error": str(exc)[:1000],
        }
    finally:
        temporary.unlink(missing_ok=True)


def crawl(plan_path: Path, corpus_root: Path, workers: int,
          limit: int | None = None, doc_ids: set[str] | None = None,
          force: bool = False) -> list[dict]:
    sources = load_jsonl(plan_path)
    errors = validate_source_plan(sources)
    if errors:
        raise ValueError("invalid source plan:\n" + "\n".join(errors))
    if doc_ids:
        sources = [source for source in sources if source["doc_id"] in doc_ids]
        missing = doc_ids - {source["doc_id"] for source in sources}
        if missing:
            raise ValueError(f"unknown doc ids: {sorted(missing)}")
    if limit is not None:
        sources = sources[:limit]

    catalog_path = corpus_root / "sources/catalog.jsonl"
    existing = _load_existing_catalog(catalog_path)
    jobs = [
        (source, index, existing.get((source["doc_id"], f"S{index}")))
        for source in sources
        for index in range(1, len(source["urls"]) + 1)
    ]
    records = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(_scrape_one, source, index, corpus_root, old, force):
            (source["doc_id"], index)
            for source, index, old in jobs
        }
        for future in as_completed(futures):
            doc_id, index = futures[future]
            record = future.result()
            records.append(record)
            print(f"[{record['status']}] {doc_id} S{index}", flush=True)

    # 保留未参与本轮筛选的既有记录，便于断点续跑和单文档重抓。
    selected_keys = {(record["doc_id"], record["source_id"]) for record in records}
    # 单文档/limit 运行保留其他 catalog 项；完整 plan 运行则清除已不在计划中的旧记录。
    if doc_ids or limit is not None:
        records.extend(record for key, record in existing.items() if key not in selected_keys)
    records.sort(key=lambda value: (value["doc_id"], value["source_id"]))
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    catalog_path.write_text(
        "".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )
    return records


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, default=DEFAULT_CORPUS / "source-plan.jsonl")
    parser.add_argument("--corpus-root", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--doc-id", action="append", default=[])
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.workers < 1 or args.workers > 2:
        parser.error("--workers must be between 1 and the current Firecrawl limit (2)")
    records = crawl(
        args.plan, args.corpus_root, args.workers, args.limit,
        set(args.doc_id) or None, args.force,
    )
    counts: dict[str, int] = {}
    for record in records:
        counts[record["status"]] = counts.get(record["status"], 0) + 1
    print(json.dumps(counts, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
