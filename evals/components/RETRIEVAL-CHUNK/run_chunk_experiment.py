#!/usr/bin/env python3
"""chunk 大小对照实验：固定 embedding 模型和查询集，只改 chunk 大小。

单变量：chunk 字符数（含整页不切一档）。
其余固定：模型、语料、查询、重叠比例、相似度度量、top-k。

ground truth 标注在文档级。chunk 命中后归约到所属文档再算指标，
否则 chunk 边界随档位变化会让不同档的指标失去可比性。
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
WIKI = HERE.parent.parent.parent / "wiki"

OLLAMA_URL = "http://localhost:11434/api/embed"
DEFAULT_MODEL = "bge-m3:latest"
# 整页档用 0 表示不切分
DEFAULT_SIZES = (200, 400, 800, 1600, 0)
OVERLAP_RATIO = 0.15
TOP_KS = (1, 3, 5)


def embed(texts: list[str], model: str, retries: int = 3) -> list[list[float]]:
    """批量调用 ollama embedding。带重试：runner 偶发崩溃时不至于整轮失败。"""
    body = json.dumps({"model": model, "input": texts}).encode()
    last = None
    for attempt in range(retries):
        req = urllib.request.Request(
            OLLAMA_URL, data=body, headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read())["embeddings"]
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            last = exc
            time.sleep(1 + attempt)
    raise RuntimeError(f"embedding failed after {retries} attempts: {last}")


# ollama 的 embedding 批次受模型上下文限制，且约束的是**整批文本 token 总和**
# 而非单条长度（实测 bge-m3：单条 6000 字符可过，但 32 条 × 6000 字符报
# "input length exceeds the context length"）。因此按字符预算动态分批。
BATCH_CHAR_BUDGET = 6000
MAX_BATCH_ITEMS = 64


def embed_all(texts: list[str], model: str) -> list[list[float]]:
    out: list[list[float]] = []
    cur: list[str] = []
    cur_chars = 0
    for t in texts:
        if cur and (cur_chars + len(t) > BATCH_CHAR_BUDGET or len(cur) >= MAX_BATCH_ITEMS):
            out.extend(embed(cur, model))
            cur, cur_chars = [], 0
        cur.append(t)
        cur_chars += len(t)
    if cur:
        out.extend(embed(cur, model))
    return out


def load_docs() -> dict[str, str]:
    docs = {}
    for path in sorted(WIKI.rglob("*.md")):
        rel = path.relative_to(WIKI).as_posix()
        docs[rel] = path.read_text(errors="ignore")
    return docs


# 整页档的硬截断上限。bge-m3 上下文为 8k token，但中文字符的 token 密度差异很大：
# 实测 wiki/industries/六氟磷酸锂.md（化学式与数字密集）在 3500 字符即超限，
# 约 2.3 token/字符，是普通中文页面的两倍多。故取 3000 这一全语料安全值。
# 截断是整页方案的真实代价，不是实验缺陷，因此记录截断页数而非静默处理。
PAGE_TRUNCATE_CHARS = 3000


def chunk_text(text: str, size: int) -> list[str]:
    """按字符切分。size=0 表示整页一个 chunk（超长则截断）。"""
    text = text.strip()
    if size <= 0:
        return [text[:PAGE_TRUNCATE_CHARS]] if text else []
    step = max(1, size - int(size * OVERLAP_RATIO))
    out = []
    for i in range(0, len(text), step):
        piece = text[i : i + size].strip()
        # 末尾残片太短则丢弃，避免产生无语义的碎块
        if len(piece) >= 40:
            out.append(piece)
        if i + size >= len(text):
            break
    return out


def build_index(docs: dict[str, str], size: int, model: str):
    chunks, owners = [], []
    truncated = 0
    for rel, text in docs.items():
        if size <= 0 and len(text.strip()) > PAGE_TRUNCATE_CHARS:
            truncated += 1
        for piece in chunk_text(text, size):
            chunks.append(piece)
            owners.append(rel)
    t0 = time.time()
    vecs = embed_all(chunks, model)
    build_s = time.time() - t0
    norms = [math.sqrt(sum(x * x for x in v)) or 1.0 for v in vecs]
    return chunks, owners, vecs, norms, build_s, truncated


def rank_docs(qv, vecs, norms, owners) -> list[str]:
    """检索 chunk，再归约到文档级：每篇文档取其最高分 chunk 作为文档得分。"""
    qn = math.sqrt(sum(x * x for x in qv)) or 1.0
    best: dict[str, float] = {}
    for i, v in enumerate(vecs):
        s = sum(a * b for a, b in zip(qv, v)) / (qn * norms[i])
        rel = owners[i]
        if s > best.get(rel, -2.0):
            best[rel] = s
    return sorted(best, key=lambda r: -best[r])


def evaluate(queries, vecs, norms, owners, model):
    qvs = embed_all([q["query"] for q in queries], model)
    lat = []
    recalls = {k: [] for k in TOP_KS}
    rrs = []
    per_type: dict[str, list[float]] = {}
    for q, qv in zip(queries, qvs):
        t0 = time.time()
        ranked = rank_docs(qv, vecs, norms, owners)
        lat.append(time.time() - t0)
        gt = set(q["ground_truth"])
        for k in TOP_KS:
            hit = len(gt & set(ranked[:k]))
            recalls[k].append(hit / len(gt))
        rr = 0.0
        for idx, rel in enumerate(ranked, 1):
            if rel in gt:
                rr = 1.0 / idx
                break
        rrs.append(rr)
        per_type.setdefault(q["type"], []).append(rr)
    return {
        **{f"recall@{k}": round(statistics.mean(v), 3) for k, v in recalls.items()},
        "MRR": round(statistics.mean(rrs), 3),
        "mrr_by_type": {t: round(statistics.mean(v), 3) for t, v in sorted(per_type.items())},
        "query_ms": round(1000 * statistics.mean(lat), 2),
        "per_query_rr": {q["id"]: round(r, 3) for q, r in zip(queries, rrs)},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--sizes", type=int, nargs="+", default=list(DEFAULT_SIZES))
    ap.add_argument("--out", default=str(HERE / "results" / "chunk_comparison.json"))
    args = ap.parse_args()

    docs = load_docs()
    queries = json.loads((HERE / "queries.json").read_text())["queries"]
    print(f"语料 {len(docs)} 篇，查询 {len(queries)} 条，模型 {args.model}\n")

    rows = []
    for size in args.sizes:
        label = "整页" if size <= 0 else str(size)
        chunks, owners, vecs, norms, build_s, truncated = build_index(docs, size, args.model)
        metrics = evaluate(queries, vecs, norms, owners, args.model)
        avg_len = round(statistics.mean([len(c) for c in chunks]))
        row = {
            "chunk_size": label,
            "chunk_count": len(chunks),
            "avg_chunk_chars": avg_len,
            "truncated_pages": truncated,
            "build_s": round(build_s, 1),
            "index_mb": round(len(vecs) * len(vecs[0]) * 4 / 1024 / 1024, 2),
            **metrics,
        }
        rows.append(row)
        print(
            f"chunk={label:>4}  n={len(chunks):>5}  R@1={row['recall@1']:.3f} "
            f"R@3={row['recall@3']:.3f} R@5={row['recall@5']:.3f} "
            f"MRR={row['MRR']:.3f}  建索引={row['build_s']}s  {row['index_mb']}MB"
        )
        print(f"       按类型 MRR: {row['mrr_by_type']}")
        if truncated:
            print(f"       注意：{truncated} 篇超 {PAGE_TRUNCATE_CHARS} 字符被截断")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {"model": args.model, "doc_count": len(docs),
             "query_count": len(queries), "overlap_ratio": OVERLAP_RATIO,
             "results": rows},
            ensure_ascii=False, indent=2,
        )
    )
    print(f"\n结果写入 {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
