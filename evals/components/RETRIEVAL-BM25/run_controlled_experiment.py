#!/usr/bin/env python3
"""TF-IDF / BM25 受控对照实验。

与历史脚本不同，本实验保证两种算法共享：
1. 相同的 jieba 文档 token；
2. 相同的查询 token；
3. 相同的候选文档集合；
4. 相同的正分候选过滤规则。

规模实验对每条查询始终保留全部 ground truth，再通过多次确定性抽样逐步加入
非相关文档。统计推断以 query 为聚类单位，避免把同一查询的多次抽样当作独立样本。
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import random
import statistics
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from retriever import BM25Retriever, TFIDFRetriever, load_documents, tokenize


DEFAULT_SIZES = (10, 20, 30, 46)


def controlled_query_tokens(query: dict, mode: str) -> list[str]:
    """生成共享查询 token；LLM 短语也经同一 tokenizer 拆分。"""
    if mode == "llm":
        text = " ".join(query.get("llm_keywords") or [])
    elif mode == "nl":
        text = query["query"]
    else:
        raise ValueError(f"unsupported query mode: {mode}")
    return tokenize(text)


def build_trial_corpus(all_paths: list[str], ground_truth: list[str],
                       target_size: int, query_id: str, trial: int) -> list[str]:
    """保留全部 GT，并以稳定随机顺序补入干扰文档。不同 size 形成嵌套集合。"""
    available = set(all_paths)
    missing = sorted(set(ground_truth) - available)
    if missing:
        raise ValueError(f"ground truth not found in corpus: {missing}")
    if target_size < len(set(ground_truth)):
        raise ValueError("target_size cannot be smaller than ground truth size")
    if target_size > len(all_paths):
        raise ValueError("target_size cannot exceed corpus size")

    gt = list(dict.fromkeys(ground_truth))
    distractors = sorted(available - set(gt))
    digest = hashlib.sha256(f"{query_id}:{trial}".encode()).digest()
    random.Random(int.from_bytes(digest[:8], "big")).shuffle(distractors)
    selected = set(gt + distractors[:target_size - len(gt)])
    return [path for path in all_paths if path in selected]


def _tfidf_scores(retriever: TFIDFRetriever, query_tokens: list[str]) -> list[float]:
    tf = Counter(query_tokens)
    qv = {term: count * retriever.idf.get(term, 0.0) for term, count in tf.items()}
    q_norm = math.sqrt(sum(value ** 2 for value in qv.values())) or 1.0
    scores = []
    for doc_vec in retriever.doc_vecs:
        doc_norm = math.sqrt(sum(value ** 2 for value in doc_vec.values())) or 1.0
        dot = sum(qv.get(term, 0.0) * doc_vec.get(term, 0.0) for term in qv)
        scores.append(dot / (q_norm * doc_norm))
    return scores


def _rank(paths: list[str], scores: list[float], top_k: int = 10) -> list[str]:
    # 两种算法都排除零分文档，消除历史实现中的候选集不一致。
    ranked = [(path, score) for path, score in zip(paths, scores) if score > 0]
    ranked.sort(key=lambda item: (-item[1], item[0]))
    return [path for path, _ in ranked[:top_k]]


def rank_both(paths: list[str], doc_tokens: list[list[str]],
              query_tokens: list[str], top_k: int = 10) -> tuple[list[str], list[str]]:
    """在完全相同的表示与候选集上，只替换 TF-IDF/BM25 打分公式。"""
    tfidf = TFIDFRetriever(paths, doc_tokens)
    bm25 = BM25Retriever(paths, doc_tokens)
    tfidf_ranked = _rank(paths, _tfidf_scores(tfidf, query_tokens), top_k)
    bm25_ranked = _rank(
        paths,
        [bm25._score(query_tokens, index) for index in range(len(paths))],
        top_k,
    )
    return tfidf_ranked, bm25_ranked


def _metric(ranked: list[str], ground_truth: list[str], name: str, k: int = 5) -> float:
    gt = set(ground_truth)
    if name == "recall@5":
        return sum(path in gt for path in ranked[:k]) / len(gt)
    if name == "mrr":
        return next((1.0 / rank for rank, path in enumerate(ranked, 1) if path in gt), 0.0)
    if name == "ndcg@5":
        rel = [1.0 if path in gt else 0.0 for path in ranked[:k]]
        dcg = sum(value / math.log2(index + 2) for index, value in enumerate(rel))
        ideal = sum(1.0 / math.log2(index + 2) for index in range(min(len(gt), k)))
        return dcg / ideal if ideal else 0.0
    raise ValueError(f"unsupported metric: {name}")


def _query_means(differences: dict[str, list[float]]) -> list[float]:
    return [statistics.fmean(values) for values in differences.values()]


def cluster_bootstrap(differences: dict[str, list[float]], samples: int = 5000,
                      seed: int = 20260727) -> dict[str, float]:
    """按 query 聚类 bootstrap；trial 仅先在 query 内取均值。"""
    query_means = _query_means(differences)
    if not query_means:
        raise ValueError("differences cannot be empty")
    rng = random.Random(seed)
    estimates = [
        statistics.fmean(rng.choice(query_means) for _ in query_means)
        for _ in range(samples)
    ]
    estimates.sort()
    low = estimates[int(0.025 * (samples - 1))]
    high = estimates[int(0.975 * (samples - 1))]
    return {
        "estimate": round(statistics.fmean(query_means), 6),
        "ci_low": round(low, 6),
        "ci_high": round(high, 6),
    }


def exact_sign_flip_pvalue(differences: dict[str, list[float]]) -> float:
    """对 query 级均值做精确双侧配对随机化检验。"""
    values = [value for value in _query_means(differences) if value != 0]
    if not values:
        return 1.0
    observed = abs(statistics.fmean(values))
    extreme = 0
    total = 2 ** len(values)
    for signs in itertools.product((-1, 1), repeat=len(values)):
        estimate = abs(statistics.fmean(sign * value for sign, value in zip(signs, values)))
        if estimate >= observed - 1e-12:
            extreme += 1
    return round(extreme / total, 6)


def run_experiment(modes: list[str], sizes: list[int], trials: int) -> dict:
    wiki = HERE / "fixture/wiki"
    queries = json.loads((HERE / "queries.json").read_text())["queries"]
    all_paths, all_tokens, _ = load_documents(str(wiki))
    token_by_path = dict(zip(all_paths, all_tokens))
    sizes = sorted(set(sizes))
    if sizes[-1] != len(all_paths):
        sizes.append(len(all_paths))

    output = {
        "hypothesis": (
            "若语料规模是 TF-IDF 优于 BM25 的主要原因，则在保持查询、相关文档、"
            "tokenizer 和候选集一致，仅增加干扰文档时，TF-IDF-BM25 的配对差值应呈稳定趋势。"
        ),
        "corpus_documents": len(all_paths),
        "query_count": len(queries),
        "trials_per_partial_size": trials,
        "sizes": sizes,
        "modes": {},
    }

    for mode in modes:
        mode_results = {}
        for size in sizes:
            trial_count = 1 if size == len(all_paths) else trials
            differences = {query["id"]: [] for query in queries}
            metric_values = {
                f"{algorithm}_{metric}": []
                for algorithm in ("tfidf", "bm25")
                for metric in ("recall@5", "mrr", "ndcg@5")
            }
            query_metric_values = {
                query["id"]: {key: [] for key in metric_values}
                for query in queries
            }
            for trial in range(trial_count):
                for query in queries:
                    selected = build_trial_corpus(
                        all_paths, query["ground_truth"], size, query["id"], trial,
                    )
                    selected_tokens = [token_by_path[path] for path in selected]
                    query_tokens = controlled_query_tokens(query, mode)
                    tfidf_ranked, bm25_ranked = rank_both(
                        selected, selected_tokens, query_tokens,
                    )
                    metrics = {}
                    for metric in ("recall@5", "mrr", "ndcg@5"):
                        metrics[f"tfidf_{metric}"] = _metric(
                            tfidf_ranked, query["ground_truth"], metric,
                        )
                        metrics[f"bm25_{metric}"] = _metric(
                            bm25_ranked, query["ground_truth"], metric,
                        )
                    for key, value in metrics.items():
                        metric_values[key].append(value)
                        query_metric_values[query["id"]][key].append(value)
                    differences[query["id"]].append(
                        metrics["tfidf_recall@5"] - metrics["bm25_recall@5"]
                    )

            query_differences = {
                query_id: round(statistics.fmean(values), 6)
                for query_id, values in differences.items()
            }
            mode_results[str(size)] = {
                "trials": trial_count,
                **{
                    key: round(statistics.fmean(values), 6)
                    for key, values in metric_values.items()
                },
                "paired_difference": cluster_bootstrap(differences),
                "sign_flip_pvalue": exact_sign_flip_pvalue(differences),
                "wins_ties_losses": {
                    "tfidf_wins": sum(value > 0 for value in query_differences.values()),
                    "ties": sum(value == 0 for value in query_differences.values()),
                    "bm25_wins": sum(value < 0 for value in query_differences.values()),
                },
                "query_mean_differences": query_differences,
                "query_mean_metrics": {
                    query_id: {
                        key: round(statistics.fmean(values), 6)
                        for key, values in metrics.items()
                    }
                    for query_id, metrics in query_metric_values.items()
                },
            }
        output["modes"][mode] = mode_results
    return output


def render_report(result: dict) -> str:
    lines = [
        "# TF-IDF / BM25 受控规模实验结果",
        "",
        f"- 语料：{result['corpus_documents']} 篇",
        f"- 查询：{result['query_count']} 条",
        f"- 部分规模抽样：每个规模 {result['trials_per_partial_size']} trials/query",
        "- 主要指标：Recall@5；95% CI 按查询聚类 bootstrap",
        "- 正差表示 TF-IDF 优于 BM25",
        "",
        f"机制假设：{result['hypothesis']}",
    ]
    for mode, sizes in result["modes"].items():
        lines.extend([
            "",
            f"## 查询模式：{mode}",
            "",
            "| 文档数 | TF-IDF R@5 | BM25 R@5 | 配对差值 [95% CI] | W/T/L | p |",
            "|---:|---:|---:|---:|---:|---:|",
        ])
        for size, row in sizes.items():
            diff = row["paired_difference"]
            wtl = row["wins_ties_losses"]
            lines.append(
                f"| {size} | {row['tfidf_recall@5']:.4f} | {row['bm25_recall@5']:.4f} "
                f"| {diff['estimate']:+.4f} [{diff['ci_low']:+.4f}, {diff['ci_high']:+.4f}] "
                f"| {wtl['tfidf_wins']}/{wtl['ties']}/{wtl['bm25_wins']} "
                f"| {row['sign_flip_pvalue']:.4f} |"
            )
    lines.extend([
        "",
        "## 解释边界",
        "",
        "该实验通过加入现有语料中的干扰文档测量 10–46 篇范围内的规模效应。"
        "它不能外推或证明 200–500 篇时 BM25 会反超；验证该阈值需要新增真实文档和独立查询。",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--modes", nargs="+", choices=("llm", "nl"), default=["llm", "nl"])
    parser.add_argument("--sizes", nargs="+", type=int, default=list(DEFAULT_SIZES))
    parser.add_argument("--trials", type=int, default=50)
    parser.add_argument("--output", type=Path, default=HERE / "results/controlled_comparison.json")
    parser.add_argument("--report", type=Path, default=HERE / "results/controlled_comparison.md")
    args = parser.parse_args()

    result = run_experiment(args.modes, args.sizes, args.trials)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    args.report.write_text(render_report(result))
    print(render_report(result))
    print(f"\nJSON: {args.output}\nReport: {args.report}")


if __name__ == "__main__":
    main()
