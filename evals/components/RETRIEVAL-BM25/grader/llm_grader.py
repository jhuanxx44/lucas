"""LLM 相关性 Grader —— 对每个 (query, doc) 对逐条评分 0-3。

评分标准：
  0 - 完全无关
  1 - 仅关键词匹配，内容不相关
  2 - 部分相关（提供背景信息或侧面关联）
  3 - 直接相关（核心内容能回答查询）

输入: 检索结果 + queries.json
输出: 逐对评分 + 按查询汇总的 avg relevance
"""
import json, os
from pathlib import Path
from typing import List, Dict, Any

# 评分 prompt 模板
SCORING_PROMPT = """你是检索质量评估员。请评估以下文档与查询的相关性。

查询：{query}

文档内容（前 1500 字符）：
{doc_snippet}

评分标准：
- 0：完全无关
- 1：仅有关键词重叠，但内容实质不相关
- 2：部分相关（提供背景或侧面信息，但非核心答案）
- 3：直接相关（核心内容能回答查询）

请仅输出一个数字（0/1/2/3），不要输出任何其他内容。"""


def load_queries(queries_path: str) -> Dict[str, Any]:
    with open(queries_path) as f:
        data = json.load(f)
    return {q["id"]: q for q in data["queries"]}


def read_doc_snippet(doc_path: str, wiki_root: str, max_chars: int = 1500) -> str:
    """读取文档的前 N 个字符作为评分依据。"""
    full = os.path.join(wiki_root, doc_path)
    if not os.path.exists(full):
        return "(文档不存在)"
    with open(full, encoding="utf-8") as f:
        content = f.read()
    # 跳过 frontmatter
    parts = content.split("---", 2)
    body = parts[-1] if len(parts) >= 3 else content
    # 去标题行
    body = body.strip()
    return body[:max_chars]


def score_pair_llm(query: str, doc_path: str, wiki_root: str,
                   llm_call_fn) -> Dict[str, Any]:
    """调用 LLM 对单个 (query, doc) 对评分。

    Args:
        query: 查询文本
        doc_path: 文档相对路径
        wiki_root: wiki fixture 根目录
        llm_call_fn: LLM 调用函数，签名为 fn(prompt: str) -> str

    Returns:
        {"doc": doc_path, "score": int, "raw_response": str}
    """
    snippet = read_doc_snippet(doc_path, wiki_root)
    prompt = SCORING_PROMPT.format(query=query, doc_snippet=snippet)

    response = llm_call_fn(prompt).strip()
    # 解析分数
    try:
        score = int(response[0]) if response and response[0].isdigit() else -1
    except (ValueError, IndexError):
        score = -1

    return {
        "doc": doc_path,
        "score": score,
        "raw_response": response,
    }


def evaluate_query_llm(query_id: str, query_text: str, ranked_docs: List[str],
                       wiki_root: str, llm_call_fn, top_k: int = 5) -> Dict[str, Any]:
    """对单条查询的 top-k 文档进行 LLM 评分。

    Returns:
        {"query_id": str, "scores": [...], "avg_score": float}
    """
    scores = []
    for doc_path in ranked_docs[:top_k]:
        result = score_pair_llm(query_text, doc_path, wiki_root, llm_call_fn)
        scores.append(result)

    valid = [s["score"] for s in scores if s["score"] >= 0]
    avg = sum(valid) / len(valid) if valid else 0.0

    return {
        "query_id": query_id,
        "scores": scores,
        "avg_score": avg,
        "valid_pairs": len(valid),
    }


def evaluate_all_llm(results: List[Dict[str, Any]], queries: Dict[str, Any],
                     wiki_root: str, llm_call_fn, top_k: int = 5) -> Dict[str, Any]:
    """批量 LLM 评分。

    Args:
        results: 检索结果列表
        queries: queries.json 加载的 dict
        wiki_root: wiki fixture 根目录
        llm_call_fn: LLM 调用函数
        top_k: 每个查询评分的文档数

    Returns:
        {"per_query": [...], "summary": {...}}
    """
    per_query = []
    for r in results:
        qid = r["query_id"]
        if qid not in queries:
            raise ValueError(f"Unknown query_id: {qid}")
        q = queries[qid]
        eq = evaluate_query_llm(
            qid, q["query"], r.get("ranked", []),
            wiki_root, llm_call_fn, top_k
        )
        eq["query_type"] = q["type"]
        per_query.append(eq)

    all_avgs = [e["avg_score"] for e in per_query]
    summary = {
        "total_queries": len(per_query),
        "avg_relevance": sum(all_avgs) / len(all_avgs) if all_avgs else 0.0,
        "top_k": top_k,
    }

    by_type = {}
    for e in per_query:
        t = e["query_type"]
        if t not in by_type:
            by_type[t] = []
        by_type[t].append(e["avg_score"])
    summary["by_type"] = {
        t: {"count": len(vals), "avg_relevance": sum(vals) / len(vals)}
        for t, vals in by_type.items()
    }

    return {"per_query": per_query, "summary": summary}


def format_llm_report(report: Dict[str, Any]) -> str:
    """格式化为可读报告。"""
    lines = []
    s = report["summary"]
    lines.append("=" * 60)
    lines.append("检索评估报告（LLM Grader）")
    lines.append("=" * 60)
    lines.append(f"\n总查询数: {s['total_queries']}  |  top_k: {s['top_k']}")
    lines.append(f"总体平均相关性: {s['avg_relevance']:.2f} / 3.0")

    lines.append(f"\n{'─' * 50}")
    lines.append("按查询类型:")
    for t, m in s["by_type"].items():
        lines.append(f"  {t:<12} ({m['count']}条)  avg={m['avg_relevance']:.2f}")

    lines.append(f"\n{'─' * 50}")
    lines.append("逐查询:")
    for e in report["per_query"]:
        score_details = " | ".join(
            f"{s['doc'].split('/')[-1][:15]}={s['score']}"
            for s in e["scores"]
        )
        lines.append(f"  [{e['query_id']}] {e['query_type']:<10} avg={e['avg_score']:.2f}  [{score_details}]")

    return "\n".join(lines)


# ── 离线模拟（用关键词匹配替代 LLM，用于测试流程）──
def dummy_llm_call(prompt: str) -> str:
    """占位 LLM 调用：简单检查文档是否包含查询关键词。"""
    # 从 prompt 中提取 query 和 doc_snippet
    try:
        query_line = [l for l in prompt.split("\n") if l.startswith("查询：")][0]
        doc_line = [l for l in prompt.split("\n") if l.startswith("文档内容")][0]
        query = query_line.replace("查询：", "").strip()
        doc = prompt.split("文档内容（前 1500 字符）：\n", 1)[-1].strip()

        # 简单关键词匹配模拟
        keywords = set(query.replace("？", "").replace("，", " ").split())
        match_count = sum(1 for kw in keywords if kw in doc)
        if match_count >= 3:
            return "3"
        elif match_count >= 2:
            return "2"
        elif match_count >= 1:
            return "1"
        else:
            return "0"
    except Exception:
        return "0"


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python llm_grader.py <queries.json> <results.json> [wiki_root]")
        sys.exit(1)

    wiki_root = sys.argv[3] if len(sys.argv) > 3 else "evals/components/RETRIEVAL-BM25/fixture/wiki"
    queries = load_queries(sys.argv[1])
    with open(sys.argv[2]) as f:
        results = json.load(f)

    report = evaluate_all_llm(results, queries, wiki_root, dummy_llm_call)
    print(format_llm_report(report))
