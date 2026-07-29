#!/usr/bin/env python3
"""为冻结查询集生成符合生产契约的 LLM 预分词关键词缓存。"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from harness.config import load_agent_config
from utils.json_extract import extract_json
from utils.llm_client import create_client


DEFAULT_CORPUS = ROOT / "evals/corpora/wiki-scale-v1"
PROMPT_PATH = ROOT / "prompts/evals/wiki-keyword-extract.md"


def parse_keywords(value: object) -> list[str]:
    if not isinstance(value, dict) or not isinstance(value.get("keywords"), list):
        return []
    keywords = []
    for item in value["keywords"]:
        if not isinstance(item, str):
            return []
        keyword = item.strip()
        if keyword and keyword not in keywords:
            keywords.append(keyword)
    return keywords if 2 <= len(keywords) <= 8 else []


def _prompt_body() -> str:
    text = PROMPT_PATH.read_text(encoding="utf-8")
    return text.split("---", 2)[2].strip() if text.startswith("---\n") else text


async def extract_keywords(corpus_root: Path, workers: int) -> list[dict]:
    query_path = corpus_root / "queries/all.json"
    queries = json.loads(query_path.read_text(encoding="utf-8"))["queries"]
    config = load_agent_config()
    prompt = _prompt_body()
    client = create_client(
        provider=config.provider,
        model=config.model,
        system_prompt=prompt,
        enable_thinking=False,
    )
    semaphore = asyncio.Semaphore(workers)
    cache_dir = corpus_root / "quality/query-keywords"
    cache_dir.mkdir(parents=True, exist_ok=True)

    async def extract(query: dict) -> dict:
        input_sha256 = hashlib.sha256(
            f"{getattr(client, 'model', '')}\n{prompt}\n{query['query']}".encode()
        ).hexdigest()
        cache = cache_dir / f"{query['id']}.json"
        cached = json.loads(cache.read_text(encoding="utf-8")) if cache.is_file() else None
        keywords = parse_keywords(cached.get("result")) if cached and cached.get("input_sha256") == input_sha256 else []
        if not keywords:
            async with semaphore:
                usage = None
                result = None
                for _ in range(2):
                    text, usage = await client.chat(
                        query["query"], response_mime_type="application/json", temperature=0,
                    )
                    candidate = extract_json(text)
                    if parse_keywords(candidate):
                        result = candidate
                        keywords = parse_keywords(candidate)
                        break
                if not keywords:
                    raise ValueError(f"invalid keyword output for {query['id']}")
                cache.write_text(json.dumps({
                    "query_id": query["id"], "query": query["query"],
                    "model": getattr(client, "model", ""),
                    "input_sha256": input_sha256, "result": result,
                    "prompt_tokens": getattr(usage, "prompt_tokens", 0) if usage else 0,
                    "completion_tokens": getattr(usage, "completion_tokens", 0) if usage else 0,
                }, ensure_ascii=False, indent=2), encoding="utf-8")
        return {
            **query,
            "llm_keywords": keywords,
            "llm_keyword_model": getattr(client, "model", ""),
            "llm_keyword_prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        }

    rows = await asyncio.gather(*(extract(query) for query in queries))
    dev_ids = {row["id"] for row in json.loads((corpus_root / "queries/dev.json").read_text(encoding="utf-8"))["queries"]}
    test_ids = {row["id"] for row in json.loads((corpus_root / "queries/test.json").read_text(encoding="utf-8"))["queries"]}
    for name, values in (
        ("all.json", rows),
        ("dev.json", [row for row in rows if row["id"] in dev_ids]),
        ("test.json", [row for row in rows if row["id"] in test_ids]),
    ):
        (corpus_root / "queries" / name).write_text(
            json.dumps({"queries": values}, ensure_ascii=False, indent=2), encoding="utf-8",
        )
    summary = {
        "query_count": len(rows), "model": getattr(client, "model", ""),
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "min_keywords": min(len(row["llm_keywords"]) for row in rows),
        "max_keywords": max(len(row["llm_keywords"]) for row in rows),
    }
    (corpus_root / "quality/query-keyword-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus-root", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    rows = asyncio.run(extract_keywords(args.corpus_root, args.workers))
    print(json.dumps({"queries": len(rows)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
