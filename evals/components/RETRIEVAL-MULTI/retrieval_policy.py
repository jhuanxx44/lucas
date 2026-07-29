"""Wiki 多证据召回实验的四臂排序核心。"""
from __future__ import annotations

import hashlib
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RETRIEVER_DIR = ROOT / "evals/components/RETRIEVAL-BM25"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(RETRIEVER_DIR))

from retriever import TFIDFRetriever, tokenize
from scripts.run_wiki_scale_experiment import substring_rank


ARMS = ("A", "B", "C", "D")
RRF_K = 60
SINGLE_CANDIDATES = 30
DECOMPOSED_CANDIDATES_PER_QUERY = 10
FINAL_K = 10
_FORBIDDEN_PLAN_RE = re.compile(r"(?:\.md(?:\b|$)|(?:^|/)wiki/|\bS\d+\b)", re.IGNORECASE)


def validate_query_plan(plan: object, strategy: str, forbidden_fragments: list[str] | None = None) -> list[str]:
    errors = []
    if not isinstance(plan, dict) or plan.get("strategy") != strategy:
        return ["strategy mismatch or plan is not an object"]
    rows = plan.get("queries")
    expected = (1, 1) if strategy == "single" else (2, 3)
    if not isinstance(rows, list) or not expected[0] <= len(rows) <= expected[1]:
        return [f"{strategy} requires {expected[0]}-{expected[1]} queries"]
    seen = set()
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            errors.append(f"query {index} must be an object")
            continue
        query = row.get("query")
        if not isinstance(query, str) or not query.strip() or len(query) > 80:
            errors.append(f"query {index} must contain 1-80 characters")
            continue
        normalized = " ".join(query.split()).casefold()
        if normalized in seen:
            errors.append(f"query {index} is duplicated")
        seen.add(normalized)
        if _FORBIDDEN_PLAN_RE.search(query):
            errors.append(f"query {index} contains a path or source marker")
        if not isinstance(row.get("target"), str) or not row["target"].strip():
            errors.append(f"query {index} target is required")
        entities = row.get("entities")
        if not isinstance(entities, list) or not entities or any(not isinstance(value, str) for value in entities):
            errors.append(f"query {index} entities must be a non-empty string list")
        for fragment in forbidden_fragments or []:
            if fragment and fragment.casefold() in query.casefold():
                errors.append(f"query {index} leaks a forbidden answer fragment")
    return errors


def single_plan(question: str) -> dict:
    return {
        "strategy": "single",
        "queries": [{"query": question, "target": "回答原始问题", "entities": [question]}],
    }


def rrf_merge(rankings: list[list[str]], limit: int = SINGLE_CANDIDATES) -> tuple[list[str], dict[str, dict]]:
    evidence: dict[str, dict] = {}
    for ranking in rankings:
        for rank, path in enumerate(ranking, 1):
            row = evidence.setdefault(path, {"rrf": 0.0, "hits": 0, "best_rank": rank})
            row["rrf"] += 1.0 / (RRF_K + rank)
            row["hits"] += 1
            row["best_rank"] = min(row["best_rank"], rank)
    ranked = sorted(
        evidence,
        key=lambda path: (
            -evidence[path]["rrf"], -evidence[path]["hits"],
            evidence[path]["best_rank"], path,
        ),
    )[:limit]
    return ranked, evidence


def _tfidf_scores(retriever: TFIDFRetriever, query_tokens: list[str]) -> list[float]:
    tf = Counter(query_tokens)
    qv = {term: count * retriever.idf.get(term, 0.0) for term, count in tf.items()}
    q_norm = math.sqrt(sum(value * value for value in qv.values())) or 1.0
    scores = []
    for doc_vec in retriever.doc_vecs:
        doc_norm = math.sqrt(sum(value * value for value in doc_vec.values())) or 1.0
        dot = sum(qv.get(term, 0.0) * doc_vec.get(term, 0.0) for term in qv)
        scores.append(dot / (q_norm * doc_norm))
    return scores


def rerank_candidates(all_paths: list[str], all_tokens: list[list[str]], candidates: list[str],
                      query_strings: list[str], rrf_evidence: dict[str, dict] | None = None,
                      limit: int = FINAL_K) -> tuple[list[str], dict[str, float]]:
    retriever = TFIDFRetriever(all_paths, all_tokens)
    scores_by_query = [_tfidf_scores(retriever, tokenize(query)) for query in query_strings]
    index = {path: position for position, path in enumerate(all_paths)}
    scores = {
        path: max(values[index[path]] for values in scores_by_query)
        for path in candidates
    }
    evidence = rrf_evidence or {}
    ranked = sorted(
        candidates,
        key=lambda path: (-scores[path], -evidence.get(path, {}).get("rrf", 0.0), path),
    )[:limit]
    return ranked, scores


def run_arm(arm: str, question: str, plan: dict, docs: list[tuple[str, str]],
            all_tokens: list[list[str]], final_k: int = FINAL_K) -> dict:
    if arm not in ARMS:
        raise ValueError(f"unknown arm: {arm}")
    strategy = "single" if arm in ("A", "C") else "decomposed"
    errors = validate_query_plan(plan, strategy)
    if errors:
        raise ValueError("invalid query plan: " + "; ".join(errors))
    queries = [row["query"] for row in plan["queries"]]
    per_query_k = SINGLE_CANDIDATES if strategy == "single" else DECOMPOSED_CANDIDATES_PER_QUERY
    per_query_rankings = [
        substring_rank(docs, tokenize(query), "substr_bm25", per_query_k)
        for query in queries
    ]
    if strategy == "single":
        candidates = per_query_rankings[0][:SINGLE_CANDIDATES]
        rrf_evidence = {
            path: {"rrf": 1.0 / (RRF_K + rank), "hits": 1, "best_rank": rank}
            for rank, path in enumerate(candidates, 1)
        }
    else:
        candidates, rrf_evidence = rrf_merge(per_query_rankings)
    if arm in ("A", "B"):
        ranked = candidates[:final_k]
        rerank_scores = {}
    else:
        rerank_queries = [question] if arm == "C" else queries
        ranked, rerank_scores = rerank_candidates(
            [path for path, _ in docs], all_tokens, candidates, rerank_queries,
            rrf_evidence, final_k,
        )
    return {
        "arm": arm, "strategy": strategy, "queries": queries,
        "per_query_rankings": per_query_rankings, "candidates": candidates,
        "candidate_sha256": hashlib.sha256("\n".join(sorted(candidates)).encode()).hexdigest(),
        "rrf_evidence": rrf_evidence, "rerank_scores": rerank_scores, "ranked": ranked,
    }


def protocol() -> dict:
    return {
        "version": 1, "arms": list(ARMS), "rrf_k": RRF_K,
        "single_candidates": SINGLE_CANDIDATES,
        "decomposed_candidates_per_query": DECOMPOSED_CANDIDATES_PER_QUERY,
        "final_k": FINAL_K,
        "rerank": "jieba TF-IDF cosine; current-manifest IDF; max over subqueries for D",
    }


if __name__ == "__main__":
    print(json.dumps(protocol(), ensure_ascii=False, indent=2))
