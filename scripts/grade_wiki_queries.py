#!/usr/bin/env python3
"""用双检索候选池和分层补样标注 Wiki 查询相关性。"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
RETRIEVER_DIR = ROOT / "evals/components/RETRIEVAL-BM25"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(RETRIEVER_DIR))

from retriever import BM25Retriever, TFIDFRetriever, load_documents
from utils.json_extract import extract_json
from utils.llm_client import create_client


DEFAULT_CORPUS = ROOT / "evals/corpora/wiki-scale-v1"
PROMPT_PATH = ROOT / "prompts/evals/wiki-query-grade.md"


def _frontmatter(text: str) -> dict:
    parts = text.split("---", 2)
    return yaml.safe_load(parts[1]) if len(parts) == 3 else {}


def build_candidate_pool(query: dict, all_paths: list[str], doc_texts: list[str],
                         tfidf: TFIDFRetriever, bm25: BM25Retriever,
                         top_k: int = 20) -> list[str]:
    text_by_path = dict(zip(all_paths, doc_texts))
    paths = list(query.get("relevant_paths", []))
    paths.extend(path for path, score in tfidf.search(query["query"], top_k) if score > 0)
    paths.extend(path for path, _ in bm25.search(query["query"], top_k))
    seed_domains = {
        _frontmatter(text_by_path[path]).get("industry")
        for path in query.get("relevant_paths", []) if path in text_by_path
    }
    same_domain = [
        path for path in all_paths
        if _frontmatter(text_by_path[path]).get("industry") in seed_domains
    ]
    rng = random.Random(int.from_bytes(hashlib.sha256(query["id"].encode()).digest()[:8], "big"))
    rng.shuffle(same_domain)
    paths.extend(same_domain[:3])
    random_paths = list(all_paths)
    rng.shuffle(random_paths)
    paths.extend(random_paths[:3])
    return list(dict.fromkeys(path for path in paths if path in text_by_path))


def _normalize_result(result: object, candidates: list[str]) -> dict | None:
    if not isinstance(result, dict) or not isinstance(result.get("judgments"), list):
        return None
    judgments = result["judgments"]
    by_path = {row.get("path"): row for row in judgments if isinstance(row, dict)}
    if len(by_path) != len(judgments) or set(by_path) != set(candidates):
        return None
    ordered = [dict(by_path[path]) for path in candidates]
    for row in ordered:
        if isinstance(row.get("grade"), str) and row["grade"].isdigit():
            row["grade"] = int(row["grade"])
    if not all(row.get("grade") in (0, 1, 2, 3) for row in ordered):
        return None
    return {**result, "judgments": ordered}


def _valid_result(result: object, candidates: list[str]) -> bool:
    return _normalize_result(result, candidates) is not None


def _valid_partial(result: object, candidates: list[str]) -> bool:
    if not isinstance(result, dict) or not isinstance(result.get("judgments"), list):
        return False
    rows = result["judgments"]
    paths = [row.get("path") for row in rows if isinstance(row, dict)]
    return (len(paths) == len(rows) == len(set(paths)) and set(paths) <= set(candidates)
            and all(str(row.get("grade")) in {"0", "1", "2", "3"} for row in rows))


async def grade_queries(corpus_root: Path, workers: int) -> list[dict]:
    master = corpus_root / "master/wiki"
    all_paths, all_tokens, doc_texts = load_documents(str(master))
    text_by_path = dict(zip(all_paths, doc_texts))
    tfidf = TFIDFRetriever(all_paths, all_tokens)
    bm25 = BM25Retriever(all_paths, all_tokens)
    queries = json.loads((corpus_root / "queries/all-draft.json").read_text(encoding="utf-8"))["queries"]
    prompt_text = PROMPT_PATH.read_text(encoding="utf-8")
    if prompt_text.startswith("---\n"):
        prompt_text = prompt_text.split("---", 2)[2].strip()
    client = create_client(model=os.environ.get("DEEPSEEK_MODEL"))
    semaphore = asyncio.Semaphore(workers)
    cache_dir = corpus_root / "quality/query-grading"
    cache_dir.mkdir(parents=True, exist_ok=True)

    async def grade(query: dict) -> dict:
        candidates = build_candidate_pool(query, all_paths, doc_texts, tfidf, bm25)
        parts_by_path = {}
        for path in candidates:
            text = text_by_path[path]
            frontmatter = _frontmatter(text)
            body = text.split("---", 2)[-1].split("\n## 来源", 1)[0]
            compact = " ".join(body.split())[:900]
            parts_by_path[path] = (
                f"### PATH: {path}\n标题：{frontmatter.get('title', '')}\n"
                f"摘要：{frontmatter.get('summary', '')}\n片段：{compact}"
            )

        def render_prompt(paths: list[str]) -> str:
            return (prompt_text
                    .replace("{query}", query["query"])
                    .replace("{answer}", query["answer"])
                    .replace("{candidates}", "\n\n".join(parts_by_path[path] for path in paths)))

        prompt = render_prompt(candidates)
        digest = hashlib.sha256(prompt.encode()).hexdigest()
        cache = cache_dir / f"{query['id']}.json"
        cached = json.loads(cache.read_text(encoding="utf-8")) if cache.is_file() else None
        if cached and cached.get("input_sha256") == digest and _valid_result(cached.get("result"), candidates):
            result = _normalize_result(cached["result"], candidates)
        else:
            async with semaphore:
                result = None
                usage = None
                candidate = None
                for _ in range(2):
                    text, usage = await client.generate_text(
                        prompt, response_mime_type="application/json", temperature=0,
                    )
                    candidate = extract_json(text)
                    normalized = _normalize_result(candidate, candidates)
                    if normalized is not None:
                        result = normalized
                        break
                if result is None and _valid_partial(candidate, candidates):
                    partial_rows = candidate["judgments"]
                    seen = {row["path"] for row in partial_rows}
                    missing = [path for path in candidates if path not in seen]
                    if 0 < len(missing) <= 3:
                        text, extra_usage = await client.generate_text(
                            render_prompt(missing), response_mime_type="application/json", temperature=0,
                        )
                        supplement = extract_json(text)
                        if _valid_result(supplement, missing):
                            merged = {**candidate, "judgments": partial_rows + supplement["judgments"]}
                            result = _normalize_result(merged, candidates)
                if not _valid_result(result, candidates):
                    cache.with_suffix(".invalid.json").write_text(json.dumps({
                        "candidates": candidates, "result": candidate,
                    }, ensure_ascii=False, indent=2), encoding="utf-8")
                    raise ValueError(f"invalid grading output for {query['id']}")
                cache.write_text(json.dumps({
                    "input_sha256": digest, "result": result,
                    "model": getattr(client, "model", ""),
                    "prompt_tokens": getattr(usage, "prompt_tokens", 0) if usage else 0,
                    "completion_tokens": getattr(usage, "completion_tokens", 0) if usage else 0,
                }, ensure_ascii=False, indent=2), encoding="utf-8")
        judgments = result["judgments"]
        ground_truth = [row["path"] for row in judgments if row["grade"] >= 2]
        answerable = bool(result.get("answerable")) and bool(ground_truth)
        return {
            **query,
            "type": query["type"] if ground_truth else "insufficient_evidence",
            "answer": query["answer"] if ground_truth else "现有知识库无法提供足够证据确定该问题的答案。",
            "candidate_pool": candidates,
            "judgments": judgments,
            "ground_truth": ground_truth,
            "answerable": answerable,
            "grading_notes": result.get("notes", ""),
        }

    rows = await asyncio.gather(*(grade(query) for query in queries))
    queries_dir = corpus_root / "queries"
    dev = [row for index, row in enumerate(rows) if index % 3 == 0]
    test = [row for index, row in enumerate(rows) if index % 3 != 0]
    for name, values in (("all.json", rows), ("dev.json", dev), ("test.json", test)):
        (queries_dir / name).write_text(json.dumps({"queries": values}, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {
        "query_count": len(rows), "dev_count": len(dev), "test_count": len(test),
        "answerable": sum(row["answerable"] for row in rows),
        "no_ground_truth": sum(not row["ground_truth"] for row in rows),
        "candidate_pool_min": min(len(row["candidate_pool"]) for row in rows),
        "candidate_pool_max": max(len(row["candidate_pool"]) for row in rows),
        "type_counts": dict(sorted(Counter(row["type"] for row in rows).items())),
    }
    (corpus_root / "quality/query-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus-root", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    rows = asyncio.run(grade_queries(args.corpus_root, args.workers))
    print(json.dumps({"graded_queries": len(rows)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
