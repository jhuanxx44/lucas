#!/usr/bin/env python3
"""子串 BM25 对照实验：不建索引、不依赖 jieba，直接以子串计数计算 TF/DF。

动机：查询侧已是 LLM 预分词关键词（生产已删除 NL 路径），文档侧因此不必
再用 jieba 分词——content.count(kw) 即可近似词频，免去索引/缓存及其失效问题。

与 bm25_llm 基准的唯一差异是 TF/DF 的计算方式（子串计数 vs jieba token 计数），
打分公式、k1/b 参数、查询输入（llm_keywords）、文档集完全一致。

用法: python3 run_substr_eval.py [--strip-frontmatter]
输出: results/substr_llm.json（加 --strip-frontmatter 时为 substr_nofm_llm.json）
"""
import glob, json, math, os, re, sys

K1, B, TOP_K = 1.5, 0.75, 10
HERE = os.path.dirname(os.path.abspath(__file__))
WIKI = os.path.join(HERE, "fixture", "wiki")
QUERIES = os.path.join(HERE, "queries.json")

_FM_RE = re.compile(r"---.*?---", re.DOTALL)


def load_docs(strip_frontmatter: bool):
    """与 retriever.py 的 load_documents 相同的文档集（跳过 index.md）。"""
    docs = []  # (rel_path, casefolded_text)
    for fpath in sorted(glob.glob(f"{WIKI}/**/*.md", recursive=True)):
        if fpath.endswith("index.md"):
            continue
        with open(fpath, encoding="utf-8") as f:
            text = f.read()
        if strip_frontmatter:
            text = _FM_RE.sub(" ", text)
        docs.append((os.path.relpath(fpath, WIKI), text.casefold()))
    return docs


def search(docs, keywords, avgdl):
    """子串 BM25：tf=子串出现次数，df=含子串的文档数，doc_len=字符数。"""
    N = len(docs)
    scores = []
    for rel, text in docs:
        doc_len = len(text) or 1
        scores.append([rel, 0.0, doc_len])
    for kw in keywords:
        kw = kw.casefold()
        if not kw:
            continue
        df = 0
        tfs = []
        for rel, text in docs:
            tf = text.count(kw)
            tfs.append(tf)
            if tf > 0:
                df += 1
        if df == 0:
            continue
        idf = math.log((N - df + 0.5) / (df + 0.5) + 1.0)
        for i, tf in enumerate(tfs):
            if tf == 0:
                continue
            doc_len = scores[i][2]
            scores[i][1] += idf * tf * (K1 + 1) / (tf + K1 * (1 - B + B * doc_len / avgdl))
    ranked = [(rel, s) for rel, s, _ in scores if s > 0]
    ranked.sort(key=lambda x: x[1], reverse=True)
    return ranked[:TOP_K]


def main():
    strip_fm = "--strip-frontmatter" in sys.argv
    docs = load_docs(strip_fm)
    avgdl = sum(len(t) for _, t in docs) / len(docs)
    print(f"共 {len(docs)} 篇, 平均 {avgdl:.0f} 字符/篇, strip_frontmatter={strip_fm}")

    with open(QUERIES) as f:
        queries = json.load(f)["queries"]

    results = []
    for q in queries:
        kws = q.get("llm_keywords") or q["keywords"]
        ranked = search(docs, kws, avgdl)
        results.append({
            "query_id": q["id"],
            "retriever": "substr@LLM-KW" + ("-nofm" if strip_fm else ""),
            "ranked": [p for p, _ in ranked],
            "scores": [round(s, 4) for _, s in ranked],
        })
        print(f"  [{q['id']}] {' '.join(kws)[:60]}... -> {len(ranked)} hits")

    out = os.path.join(HERE, "results",
                       "substr_nofm_llm.json" if strip_fm else "substr_llm.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"结果已写入: {out}")


if __name__ == "__main__":
    main()
