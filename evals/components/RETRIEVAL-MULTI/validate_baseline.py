#!/usr/bin/env python3
"""验证新 A 臂逐条复现上一轮生产子串 BM25 离线排名。"""
from __future__ import annotations

import json
from pathlib import Path

from retrieval_policy import run_arm, single_plan

ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / "evals/corpora/wiki-scale-v1"


def main() -> None:
    master = CORPUS / "master/wiki"
    queries = {row["id"]: row for row in json.loads((CORPUS / "queries/test.json").read_text())["queries"]}
    previous = json.loads((CORPUS / "results/offline-scale.json").read_text())["deployable_rows"]
    expected = {
        (row["query_id"], row["seed"], row["size"]): row["ranked"]
        for row in previous if row["algorithm"] == "substr_bm25"
    }
    mismatches = []
    checked = 0
    for (query_id, seed, size), ranked in expected.items():
        manifest = CORPUS / f"manifests/controlled/{query_id}/seed-{seed}/n{size:04d}.json"
        paths = json.loads(manifest.read_text())["documents"]
        docs = [(path, (master / path).read_text(encoding="utf-8").casefold()) for path in paths]
        from retriever import tokenize
        tokens = [tokenize(text) for _, text in docs]
        actual = run_arm("A", queries[query_id]["query"], single_plan(queries[query_id]["query"]), docs, tokens)["ranked"]
        checked += 1
        if actual != ranked:
            mismatches.append({"query_id": query_id, "seed": seed, "size": size, "expected": ranked, "actual": actual})
    report = {"passed": not mismatches, "checked": checked, "mismatches": mismatches}
    output = Path(__file__).resolve().parent / "results/baseline-validation.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
