#!/usr/bin/env python3
"""基于冻结 Wiki 页面生成固定查询草案。"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from utils.json_extract import extract_json
from utils.llm_client import create_client


DEFAULT_CORPUS = ROOT / "evals/corpora/wiki-scale-v1"
PROMPT_PATH = ROOT / "prompts/evals/wiki-query-generate.md"
TYPE_PATTERN = [
    "company_fact", "concept", "near_distractor", "long_tail", "synonym",
    "company_fact", "concept", "cross_document", "cross_document",
    "insufficient_evidence",
]


def _frontmatter(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8").split("---", 2)[1])


def select_pages(master: Path, count: int, seed: int = 20260727) -> list[Path]:
    pages = sorted(path for path in master.rglob("*.md") if path.name != "index.md")
    by_domain: dict[str, list[Path]] = defaultdict(list)
    for page in pages:
        by_domain[_frontmatter(page).get("industry", "unknown")].append(page)
    for domain, values in by_domain.items():
        values.sort(key=lambda page: hashlib.sha256(
            f"{seed}:{domain}:{page.relative_to(master).as_posix()}".encode()
        ).hexdigest())
    domains = sorted(by_domain, key=lambda value: (-len(by_domain[value]), value))
    selected = []
    while len(selected) < min(count, len(pages)):
        progressed = False
        for domain in domains:
            if by_domain[domain]:
                selected.append(by_domain[domain].pop(0))
                progressed = True
                if len(selected) == count:
                    break
        if not progressed:
            break
    return selected


def _prompt_body() -> str:
    text = PROMPT_PATH.read_text(encoding="utf-8")
    return text.split("---", 2)[2].strip() if text.startswith("---\n") else text


def _valid_batch(result: object, allowed: set[str]) -> bool:
    if not isinstance(result, dict) or not isinstance(result.get("queries"), list):
        return False
    rows = result["queries"]
    if len(rows) != len(TYPE_PATTERN):
        return False
    for row, expected_type in zip(rows, TYPE_PATTERN):
        if row.get("type") != expected_type or not row.get("query") or not row.get("answer"):
            return False
        paths = row.get("relevant_paths")
        if not isinstance(paths, list) or any(path not in allowed for path in paths):
            return False
        expected_count = 0 if expected_type == "insufficient_evidence" else (2 if expected_type == "cross_document" else 1)
        if len(set(paths)) != expected_count:
            return False
    return True


async def build_queries(corpus_root: Path, query_count: int, workers: int) -> list[dict]:
    if query_count < 60 or query_count % len(TYPE_PATTERN):
        raise ValueError(f"query_count must be >=60 and divisible by {len(TYPE_PATTERN)}")
    master = corpus_root / "master/wiki"
    batch_count = query_count // len(TYPE_PATTERN)
    chosen = select_pages(master, batch_count * 12)
    batches = [chosen[index * 12:(index + 1) * 12] for index in range(batch_count)]
    prompt_template = _prompt_body()
    client = create_client(model=os.environ.get("DEEPSEEK_MODEL"))
    semaphore = asyncio.Semaphore(workers)
    cache_dir = corpus_root / "quality/query-generation"
    cache_dir.mkdir(parents=True, exist_ok=True)

    async def generate(batch_index: int, pages: list[Path]) -> list[dict]:
        page_parts = []
        allowed = set()
        for page in pages:
            relative = page.relative_to(master).as_posix()
            allowed.add(relative)
            page_parts.append(f"## PATH: {relative}\n\n{page.read_text(encoding='utf-8')}")
        prompt = (prompt_template
                  .replace("{query_count}", str(len(TYPE_PATTERN)))
                  .replace("{query_types}", ", ".join(TYPE_PATTERN))
                  .replace("{pages}", "\n\n".join(page_parts)))
        digest = hashlib.sha256(prompt.encode()).hexdigest()
        cache = cache_dir / f"batch-{batch_index + 1:02d}.json"
        cached = json.loads(cache.read_text(encoding="utf-8")) if cache.is_file() else None
        if cached and cached.get("input_sha256") == digest and _valid_batch(cached.get("result"), allowed):
            return cached["result"]["queries"]
        async with semaphore:
            result = None
            usage = None
            for _ in range(2):
                text, usage = await client.generate_text(
                    prompt, response_mime_type="application/json", temperature=0,
                )
                candidate = extract_json(text)
                if _valid_batch(candidate, allowed):
                    result = candidate
                    break
            if not _valid_batch(result, allowed):
                raise ValueError(f"invalid query batch {batch_index + 1}")
            cache.write_text(json.dumps({
                "input_sha256": digest, "result": result,
                "model": getattr(client, "model", ""),
                "prompt_tokens": getattr(usage, "prompt_tokens", 0) if usage else 0,
                "completion_tokens": getattr(usage, "completion_tokens", 0) if usage else 0,
            }, ensure_ascii=False, indent=2), encoding="utf-8")
            return result["queries"]

    generated = await asyncio.gather(*(generate(index, pages) for index, pages in enumerate(batches)))
    rows = []
    for index, row in enumerate((item for batch in generated for item in batch), 1):
        rows.append({"id": f"QS-{index:03d}", **row})
    queries_dir = corpus_root / "queries"
    queries_dir.mkdir(parents=True, exist_ok=True)
    dev = [row for index, row in enumerate(rows) if index % 3 == 0]
    test = [row for index, row in enumerate(rows) if index % 3 != 0]
    for name, values in (("all-draft.json", rows), ("dev-draft.json", dev), ("test-draft.json", test)):
        (queries_dir / name).write_text(json.dumps({"queries": values}, ensure_ascii=False, indent=2), encoding="utf-8")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus-root", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--query-count", type=int, default=60)
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    rows = asyncio.run(build_queries(args.corpus_root, args.query_count, args.workers))
    print(json.dumps({"query_count": len(rows)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
