"""确定性检索 Grader —— 基于地面真相计算 recall/precision/MRR/NDCG。

输入: 检索结果 JSON（按查询分组的排序文档列表）
输出: 逐查询指标 + 汇总统计
"""
import json, math
from pathlib import Path
from typing import List, Dict, Any


def load_queries(queries_path: str) -> Dict[str, Any]:
    """加载 queries.json，返回以 query_id 为 key 的 dict。"""
    with open(queries_path) as f:
        data = json.load(f)
    return {q["id"]: q for q in data["queries"]}


def dcg(scores: List[float]) -> float:
    """Discounted Cumulative Gain。"""
    return sum(s / math.log2(i + 2) for i, s in enumerate(scores))


def ndcg(ranked_paths: List[str], ground_truth: List[str], k: int) -> float:
    """NDCG@k：将命中视为 binary relevance (1/0)。"""
    gt_set = set(ground_truth)
    # DCG of retrieved
    rel = [1.0 if p in gt_set else 0.0 for p in ranked_paths[:k]]
    dcg_val = dcg(rel)
    # Ideal DCG (all relevant docs at top)
    ideal_rel = sorted([1.0] * min(len(ground_truth), k) + [0.0] * max(0, k - len(ground_truth)), reverse=True)
    idcg_val = dcg(ideal_rel)
    return dcg_val / idcg_val if idcg_val > 0 else 0.0


def evaluate_single(query_id: str, ranked_paths: List[str], ground_truth: List[str],
                    k_values: List[int] = (1, 3, 5, 10)) -> Dict[str, Any]:
    """对单条查询计算所有指标。

    Args:
        query_id: 查询 ID
        ranked_paths: 检索返回的文档路径列表（按相关性降序）
        ground_truth: 地面真相文档路径列表
        k_values: 计算 recall/precision@k 的 k 值列表

    Returns:
        dict: 包含 recall@k, precision@k, MRR, NDCG@k
    """
    gt_set = set(ground_truth)
    metrics = {"query_id": query_id, "total_gt": len(gt_set)}

    # recall@k & precision@k
    for k in k_values:
        top_k = ranked_paths[:k]
        hits = sum(1 for p in top_k if p in gt_set)
        metrics[f"recall@{k}"] = hits / len(gt_set) if gt_set else 0.0
        metrics[f"precision@{k}"] = hits / min(k, len(top_k)) if top_k else 0.0

    # MRR
    for rank, path in enumerate(ranked_paths, start=1):
        if path in gt_set:
            metrics["MRR"] = 1.0 / rank
            break
    else:
        metrics["MRR"] = 0.0

    # NDCG@k
    for k in k_values:
        metrics[f"NDCG@{k}"] = ndcg(ranked_paths, ground_truth, k)

    return metrics


def evaluate_all(results: List[Dict[str, Any]], queries: Dict[str, Any],
                  k_values: List[int] = (1, 3, 5, 10)) -> Dict[str, Any]:
    """批量评估所有查询。

    Args:
        results: 检索结果列表，每项包含 query_id 和 ranked 文档路径列表
        queries: 从 queries.json 加载的查询 dict
        k_values: k 值列表

    Returns:
        dict: per_query（逐条指标）+ summary（汇总）
    """
    per_query = []
    for r in results:
        qid = r["query_id"]
        if qid not in queries:
            raise ValueError(f"Unknown query_id: {qid}")
        gt = queries[qid]["ground_truth"]
        ranked = r.get("ranked", [])
        m = evaluate_single(qid, ranked, gt, k_values)
        m["query_type"] = queries[qid]["type"]
        per_query.append(m)

    # 汇总：按 k 值取平均
    summary = {"total_queries": len(per_query)}
    for k in k_values:
        for metric in [f"recall@{k}", f"precision@{k}", f"NDCG@{k}"]:
            vals = [m[metric] for m in per_query]
            summary[f"avg_{metric}"] = sum(vals) / len(vals) if vals else 0.0
    summary["avg_MRR"] = sum(m["MRR"] for m in per_query) / len(per_query) if per_query else 0.0

    # 按查询类型分组汇总
    by_type = {}
    for m in per_query:
        t = m["query_type"]
        if t not in by_type:
            by_type[t] = []
        by_type[t].append(m)
    summary["by_type"] = {}
    for t, items in by_type.items():
        summary["by_type"][t] = {
            "count": len(items),
            "avg_recall@5": sum(m["recall@5"] for m in items) / len(items),
            "avg_precision@5": sum(m["precision@5"] for m in items) / len(items),
            "avg_MRR": sum(m["MRR"] for m in items) / len(items),
        }

    return {"per_query": per_query, "summary": summary}


def format_report(report: Dict[str, Any]) -> str:
    """将评估报告格式化为可读文本。"""
    lines = []
    s = report["summary"]

    lines.append("=" * 60)
    lines.append("检索评估报告（确定性 Grader）")
    lines.append("=" * 60)
    lines.append(f"\n总查询数: {s['total_queries']}")
    lines.append(f"\n{'指标':<18} {'@1':>8} {'@3':>8} {'@5':>8} {'@10':>8}")
    lines.append("-" * 50)
    for metric_name in ["recall", "precision", "NDCG"]:
        vals = [f"{s[f'avg_{metric_name}@{k}']:.4f}" for k in (1, 3, 5, 10)]
        lines.append(f"avg_{metric_name:<13} {vals[0]:>8} {vals[1]:>8} {vals[2]:>8} {vals[3]:>8}")
    lines.append(f"\navg_MRR: {s['avg_MRR']:.4f}")

    lines.append(f"\n{'─' * 50}")
    lines.append("按查询类型:")
    lines.append(f"  {'类型':<12} {'数量':>4} {'recall@5':>10} {'prec@5':>9} {'MRR':>8}")
    for t, m in s["by_type"].items():
        lines.append(f"  {t:<12} {m['count']:>4} {m['avg_recall@5']:>10.4f} {m['avg_precision@5']:>9.4f} {m['avg_MRR']:>8.4f}")

    lines.append(f"\n{'─' * 50}")
    lines.append("逐查询:")
    for m in report["per_query"]:
        lines.append(f"  [{m['query_id']}] {m['query_type']:<10} "
                     f"R@5={m['recall@5']:.3f} P@5={m['precision@5']:.3f} "
                     f"MRR={m['MRR']:.3f}")

    return "\n".join(lines)


# ── CLI ──
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python deterministic.py <queries.json> <results.json>")
        sys.exit(1)

    queries = load_queries(sys.argv[1])
    with open(sys.argv[2]) as f:
        results = json.load(f)

    report = evaluate_all(results, queries)
    print(format_report(report))
