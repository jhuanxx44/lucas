#!/usr/bin/env python3
"""运行 Wiki 规模实验的离线检索矩阵与可部署排序核心对照。"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RETRIEVER_DIR = ROOT / "evals/components/RETRIEVAL-BM25"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(RETRIEVER_DIR))

from retriever import BM25Retriever, TFIDFRetriever, load_documents, tokenize


DEFAULT_CORPUS = ROOT / "evals/corpora/wiki-scale-v1"
SIZES = (50, 100, 200, 500)
SEEDS = (1, 2, 3, 4, 5)
METRICS = ("recall@5", "recall@10", "mrr", "ndcg@5", "ndcg@10")


def metric(ranked: list[str], judgments: dict[str, int], name: str) -> float | None:
    relevant = {path for path, grade in judgments.items() if grade >= 2}
    if not relevant:
        return None
    if name.startswith("recall@"):
        k = int(name.split("@")[1])
        return sum(path in relevant for path in ranked[:k]) / len(relevant)
    if name == "mrr":
        return next((1 / index for index, path in enumerate(ranked, 1) if path in relevant), 0.0)
    if name.startswith("ndcg@"):
        k = int(name.split("@")[1])
        gains = [(2 ** judgments.get(path, 0) - 1) for path in ranked[:k]]
        dcg = sum(gain / math.log2(index + 2) for index, gain in enumerate(gains))
        ideal_gains = sorted((2 ** grade - 1 for grade in judgments.values() if grade >= 2), reverse=True)[:k]
        ideal = sum(gain / math.log2(index + 2) for index, gain in enumerate(ideal_gains))
        return dcg / ideal if ideal else None
    raise ValueError(f"unsupported metric: {name}")


def _tfidf_ranked(retriever: TFIDFRetriever, query_tokens: list[str], top_k: int = 10) -> list[str]:
    tf = Counter(query_tokens)
    qv = {term: count * retriever.idf.get(term, 0.0) for term, count in tf.items()}
    q_norm = math.sqrt(sum(value * value for value in qv.values())) or 1.0
    scored = []
    for path, doc_vec in zip(retriever.doc_paths, retriever.doc_vecs):
        doc_norm = math.sqrt(sum(value * value for value in doc_vec.values())) or 1.0
        score = sum(qv.get(term, 0.0) * doc_vec.get(term, 0.0) for term in qv) / (q_norm * doc_norm)
        if score > 0:
            scored.append((path, score))
    scored.sort(key=lambda item: (-item[1], item[0]))
    return [path for path, _ in scored[:top_k]]


def substring_rank(docs: list[tuple[str, str]], keywords: list[str], algorithm: str,
                   top_k: int = 10) -> list[str]:
    n = len(docs)
    if not n or not keywords:
        return []
    doc_lens = [len(text) or 1 for _, text in docs]
    avgdl = statistics.fmean(doc_lens)
    scores = [0.0] * n
    idfs = {}
    tfs_by_term = {}
    for term in dict.fromkeys(keyword.casefold() for keyword in keywords if keyword):
        tfs = [text.count(term) for _, text in docs]
        df = sum(tf > 0 for tf in tfs)
        if not df:
            continue
        idfs[term] = math.log((n - df + 0.5) / (df + 0.5) + 1)
        tfs_by_term[term] = tfs
    if algorithm == "substr_bm25":
        for term, tfs in tfs_by_term.items():
            for index, tf in enumerate(tfs):
                if tf:
                    scores[index] += idfs[term] * tf * 2.5 / (
                        tf + 1.5 * (0.25 + 0.75 * doc_lens[index] / avgdl)
                    )
    elif algorithm == "substr_tfidf":
        query_vector = {term: idfs[term] for term in idfs}
        query_norm = math.sqrt(sum(value * value for value in query_vector.values())) or 1.0
        for index in range(n):
            vector = {
                term: (tfs[index] / doc_lens[index]) * idfs[term]
                for term, tfs in tfs_by_term.items() if tfs[index]
            }
            doc_norm = math.sqrt(sum(value * value for value in vector.values())) or 1.0
            scores[index] = sum(query_vector.get(term, 0) * value for term, value in vector.items()) / (query_norm * doc_norm)
    else:
        raise ValueError(f"unknown substring algorithm: {algorithm}")
    ranked = [(path, score) for (path, _), score in zip(docs, scores) if score > 0]
    ranked.sort(key=lambda item: (-item[1], item[0]))
    return [path for path, _ in ranked[:top_k]]


def bootstrap_ci(query_differences: dict[str, list[float]], samples: int = 5000) -> dict:
    means = [statistics.fmean(values) for values in query_differences.values() if values]
    if not means:
        return {"estimate": 0.0, "ci_low": 0.0, "ci_high": 0.0}
    rng = random.Random(20260727)
    estimates = sorted(statistics.fmean(rng.choice(means) for _ in means) for _ in range(samples))
    return {
        "estimate": round(statistics.fmean(means), 6),
        "ci_low": round(estimates[int(0.025 * (samples - 1))], 6),
        "ci_high": round(estimates[int(0.975 * (samples - 1))], 6),
    }


def _row(query: dict, track: str, seed: int, size: int, algorithm: str,
         ranked: list[str], build_ms: float, search_ms: float) -> dict:
    judgments = {item["path"]: item["grade"] for item in query["judgments"]}
    return {
        "query_id": query["id"], "query_type": query["type"], "track": track,
        "seed": seed, "size": size, "algorithm": algorithm, "ranked": ranked,
        "no_result": not ranked, "build_ms": round(build_ms, 4), "search_ms": round(search_ms, 4),
        **{name: metric(ranked, judgments, name) for name in METRICS},
    }


def query_keywords(query: dict) -> list[str]:
    keywords = query.get("llm_keywords")
    if not isinstance(keywords, list) or not keywords or any(
        not isinstance(keyword, str) or not keyword.strip() for keyword in keywords
    ):
        raise ValueError(f"{query.get('id', '<unknown>')} missing cached llm_keywords")
    return [keyword.strip() for keyword in keywords]


def run(corpus_root: Path) -> dict:
    master = corpus_root / "master/wiki"
    all_paths, all_tokens, all_texts = load_documents(str(master))
    token_by_path = dict(zip(all_paths, all_tokens))
    text_by_path = {path: text.casefold() for path, text in zip(all_paths, all_texts)}
    queries = json.loads((corpus_root / "queries/test.json").read_text(encoding="utf-8"))["queries"]
    rows = []
    deployable_rows = []

    for track in ("controlled", "natural"):
        for query in queries:
            raw_keywords = query_keywords(query)
            # 纯公式对照仍让查询与文档共享 tokenizer；输入语义来自固定 LLM 关键词，
            # 不再从自然语言问句生成查询 token。
            query_tokens = tokenize(" ".join(raw_keywords))
            for seed in SEEDS:
                for size in SIZES:
                    if track == "controlled":
                        manifest_path = corpus_root / f"manifests/controlled/{query['id']}/seed-{seed}/n{size:04d}.json"
                    else:
                        manifest_path = corpus_root / f"manifests/natural/seed-{seed}/n{size:04d}.json"
                    docs = json.loads(manifest_path.read_text(encoding="utf-8"))["documents"]
                    tokens = [token_by_path[path] for path in docs]
                    start = time.perf_counter()
                    tfidf = TFIDFRetriever(docs, tokens)
                    tfidf_build = (time.perf_counter() - start) * 1000
                    start = time.perf_counter()
                    tfidf_ranked = _tfidf_ranked(tfidf, query_tokens)
                    tfidf_search = (time.perf_counter() - start) * 1000
                    start = time.perf_counter()
                    bm25 = BM25Retriever(docs, tokens)
                    bm25_build = (time.perf_counter() - start) * 1000
                    start = time.perf_counter()
                    bm25_ranked = [path for path, _ in bm25.search(" ".join(raw_keywords), 10)]
                    bm25_search = (time.perf_counter() - start) * 1000
                    rows.append(_row(query, track, seed, size, "tfidf", tfidf_ranked, tfidf_build, tfidf_search))
                    rows.append(_row(query, track, seed, size, "bm25", bm25_ranked, bm25_build, bm25_search))
                    if track == "controlled":
                        substring_docs = [(path, text_by_path[path]) for path in docs]
                        for algorithm in ("substr_bm25", "substr_tfidf"):
                            start = time.perf_counter()
                            ranked = substring_rank(substring_docs, raw_keywords, algorithm)
                            elapsed = (time.perf_counter() - start) * 1000
                            deployable_rows.append(_row(query, track, seed, size, algorithm, ranked, 0, elapsed))

    def aggregate(source_rows: list[dict]) -> list[dict]:
        grouped: dict[tuple, list[dict]] = defaultdict(list)
        for row in source_rows:
            grouped[(row["track"], row["algorithm"], row["size"])].append(row)
        result = []
        for (track, algorithm, size), values in sorted(grouped.items()):
            answerable = [row for row in values if row["recall@5"] is not None]
            result.append({
                "track": track, "algorithm": algorithm, "size": size,
                "observations": len(values), "answerable_observations": len(answerable),
                **{name: round(statistics.fmean(row[name] for row in answerable), 6) for name in METRICS},
                "no_result_rate": round(statistics.fmean(row["no_result"] for row in values), 6),
                "build_ms_mean": round(statistics.fmean(row["build_ms"] for row in values), 4),
                "search_ms_mean": round(statistics.fmean(row["search_ms"] for row in values), 4),
            })
        return result

    comparisons = []
    for track in ("controlled", "natural"):
        for size in SIZES:
            for metric_name in METRICS:
                by_key = {(row["query_id"], row["seed"], row["algorithm"]): row for row in rows if row["track"] == track and row["size"] == size}
                differences: dict[str, list[float]] = defaultdict(list)
                seed_means = {}
                for query in queries:
                    for seed in SEEDS:
                        left = by_key[(query["id"], seed, "tfidf")][metric_name]
                        right = by_key[(query["id"], seed, "bm25")][metric_name]
                        if left is not None and right is not None:
                            differences[query["id"]].append(left - right)
                for seed in SEEDS:
                    values = [
                        by_key[(query["id"], seed, "tfidf")][metric_name] - by_key[(query["id"], seed, "bm25")][metric_name]
                        for query in queries
                        if by_key[(query["id"], seed, "tfidf")][metric_name] is not None
                    ]
                    seed_means[str(seed)] = round(statistics.fmean(values), 6) if values else 0
                comparisons.append({
                    "track": track, "size": size, "metric": metric_name,
                    "tfidf_minus_bm25": bootstrap_ci(differences), "seed_means": seed_means,
                })

    output = {
        "protocol": {
            "split": "test", "query_count": len(queries), "sizes": list(SIZES), "seeds": list(SEEDS),
            "query_contract": "cached LLM pre-tokenized keywords only; NL path removed",
            "keyword_model": queries[0].get("llm_keyword_model", ""),
            "keyword_prompt_sha256": queries[0].get("llm_keyword_prompt_sha256", ""),
            "representation": "cached LLM keywords, shared jieba tokens for formula-only comparison; positive-score filtering; graded relevance 0-3",
        },
        "aggregate": aggregate(rows), "comparisons": comparisons,
        "deployable_aggregate": aggregate(deployable_rows),
        "rows": rows, "deployable_rows": deployable_rows,
    }
    return output


def render_report(result: dict) -> str:
    lines = [
        "# Wiki 规模离线检索结果", "",
        "test 集；输入为固定 LLM 预分词关键词，TF-IDF 与 BM25 使用相同 jieba 表示和正分过滤。差值为 TF-IDF - BM25。", "",
        "## 受控干扰轨道", "",
        "| 规模 | TF-IDF R@5 | BM25 R@5 | 差值 [95% CI] | TF-IDF NDCG@10 | BM25 NDCG@10 |", "|---:|---:|---:|---:|---:|---:|",
    ]
    aggregates = {(row["track"], row["algorithm"], row["size"]): row for row in result["aggregate"]}
    comparisons = {(row["track"], row["size"], row["metric"]): row for row in result["comparisons"]}
    for size in SIZES:
        tfidf = aggregates[("controlled", "tfidf", size)]
        bm25 = aggregates[("controlled", "bm25", size)]
        diff = comparisons[("controlled", size, "recall@5")]["tfidf_minus_bm25"]
        lines.append(
            f"| {size} | {tfidf['recall@5']:.3f} | {bm25['recall@5']:.3f} | "
            f"{diff['estimate']:+.3f} [{diff['ci_low']:+.3f}, {diff['ci_high']:+.3f}] | "
            f"{tfidf['ndcg@10']:.3f} | {bm25['ndcg@10']:.3f} |"
        )
    lines.extend(["", "## 自然增长轨道", "", "| 规模 | TF-IDF R@5 | BM25 R@5 | TF-IDF MRR | BM25 MRR |", "|---:|---:|---:|---:|---:|"])
    for size in SIZES:
        left = aggregates[("natural", "tfidf", size)]
        right = aggregates[("natural", "bm25", size)]
        lines.append(f"| {size} | {left['recall@5']:.3f} | {right['recall@5']:.3f} | {left['mrr']:.3f} | {right['mrr']:.3f} |")
    lines.extend(["", "## 可部署排序核心", "", "| 规模 | 子串 TF-IDF R@5 | 生产子串 BM25 R@5 |", "|---:|---:|---:|"])
    deploy = {(row["algorithm"], row["size"]): row for row in result["deployable_aggregate"]}
    for size in SIZES:
        lines.append(f"| {size} | {deploy[('substr_tfidf', size)]['recall@5']:.3f} | {deploy[('substr_bm25', size)]['recall@5']:.3f} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus-root", type=Path, default=DEFAULT_CORPUS)
    args = parser.parse_args()
    result = run(args.corpus_root)
    output_dir = args.corpus_root / "results"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "offline-scale.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    report = render_report(result)
    (output_dir / "offline-scale.md").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
