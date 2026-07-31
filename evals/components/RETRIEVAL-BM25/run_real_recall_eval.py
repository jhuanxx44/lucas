#!/usr/bin/env python3
"""真实 wiki_recall 对照实验：NL（jieba 分词）vs KW（LLM 提取关键词）。

注意：recall_wiki 已移除 NL 路径，此脚本仅保留作为实验记录。
KW 路径仍可运行：LLM 提取关键词 → recall_wiki(keyword_string)。
"""
import asyncio, json, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from utils.wiki_core import recall_wiki
from utils.llm_client import create_client

WIKI_ROOT = os.path.join(os.path.dirname(__file__), "fixture", "wiki")
QUERIES_PATH = os.path.join(os.path.dirname(__file__), "queries.json")
OUT_DIR = os.path.join(os.path.dirname(__file__), "results")
MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")

# llm-weight: light
KW_SYSTEM_PROMPT = """你是一个中文关键词提取器。给定一个自然语言问题，提取用于文档检索的关键词。

规则：
1. 只提取实体名（公司、产品、技术、概念）、专业术语、领域关键词
2. 不要提取疑问词、语气词、通用动词（"是什么""有哪些""如何"等）
3. 同义词和缩写同时保留（如"GPU"和"图形处理器"）
4. 输出格式：关键词用空格分隔，一行输出，不要任何解释
5. 每条 3-8 个关键词"""


async def extract_llm_keywords(client, query: str) -> list[str]:
    try:
        text, _ = await client.generate_text(query)
        keywords = [k.strip() for k in text.split() if k.strip()]
        if keywords:
            return keywords
    except Exception as e:
        print(f"  [LLM ERROR] {e}")
    return []


async def main():
    with open(QUERIES_PATH) as f:
        queries_data = json.load(f)

    client = create_client(MODEL, instructions=KW_SYSTEM_PROMPT)
    os.makedirs(OUT_DIR, exist_ok=True)

    kw_results = []

    for q in queries_data["queries"]:
        qid = q["id"]
        nl_text = q["query"]

        llm_kw = await extract_llm_keywords(client, nl_text)
        if not llm_kw:
            print(f"[{qid}] LLM extraction failed, skipping")
            continue

        kw_str = " ".join(llm_kw)
        pages = recall_wiki(WIKI_ROOT, kw_str)
        kw_results.append({
            "query_id": qid,
            "retriever": f"wiki_recall_kw_llm@{MODEL}",
            "llm_keywords": llm_kw,
            "ranked": [p["path"] for p in pages],
            "scores": [p.get("score", 0) for p in pages],
        })
        print(f"[{qid}] LLM-KW: {llm_kw} → {len(pages)}p")

    kw_path = os.path.join(OUT_DIR, "real_kw_llm.json")
    with open(kw_path, "w", encoding="utf-8") as f:
        json.dump(kw_results, f, ensure_ascii=False, indent=2)

    # Grader
    sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
    from grader.deterministic import evaluate_all, load_queries
    queries = load_queries(QUERIES_PATH)

    print("\n" + "=" * 64)
    print(f"{'Mode':<30} {'R@5':>8} {'P@5':>8} {'MRR':>8} {'NDCG@5':>8}")
    print("-" * 64)

    results = json.load(open(kw_path))
    report = evaluate_all(results, queries)
    s = report["summary"]
    print(f"{'KW (LLM keywords → BM25)':<30} {s['avg_recall@5']:>8.4f} {s['avg_precision@5']:>8.4f} "
          f"{s['avg_MRR']:>8.4f} {s['avg_NDCG@5']:>8.4f}")


if __name__ == "__main__":
    asyncio.run(main())
