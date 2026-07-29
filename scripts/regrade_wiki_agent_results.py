#!/usr/bin/env python3
"""按最终确定性规则重判已完成的 Wiki Agent trial。"""
from __future__ import annotations

import json
import statistics
from pathlib import Path

from run_wiki_agent_experiment import SIZES, TASKS, render_report, score_answer


ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "evals/corpora/wiki-scale-v1"


def main() -> None:
    path = CORPUS / "results/agent-scale.json"
    result = json.loads(path.read_text(encoding="utf-8"))
    for row in result["rows"]:
        row["original_harness_success"] = row["success"]
        scores = score_answer(row["task_id"], row.get("answer"))
        row.update(scores)
        row["success"] = scores["outcome_passed"] and not row.get("error")
    aggregates = []
    for task_id in TASKS:
        for size in SIZES:
            for retriever in ("substr_bm25", "jieba_tfidf"):
                values = [
                    row for row in result["rows"]
                    if row["task_id"] == task_id and row["size"] == size
                    and row["retriever"] == retriever
                ]
                aggregates.append({
                    "task_id": task_id, "size": size, "retriever": retriever,
                    "trials": len(values),
                    "success_rate": statistics.fmean(row["success"] for row in values),
                    "fact_coverage_mean": statistics.fmean(row["fact_coverage"] for row in values),
                    "evidence_coverage_mean": statistics.fmean(row["evidence_coverage"] for row in values),
                    "unsupported_evidence_rate": statistics.fmean(row["unsupported_evidence"] for row in values),
                    "steps_mean": statistics.fmean(row["steps"] for row in values),
                    "tool_calls_mean": statistics.fmean(row["tool_calls"] for row in values),
                    "tokens_mean": statistics.fmean(row["prompt_tokens"] + row["completion_tokens"] for row in values),
                    "cost_usd_mean": statistics.fmean(row["cost_usd"] for row in values),
                    "latency_seconds_mean": statistics.fmean(row["latency_seconds"] for row in values),
                })
    result["aggregates"] = aggregates
    result["protocol"]["grader"] = "deterministic fact-group coverage + normalized evidence-path set"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    report = render_report(result)
    (CORPUS / "results/agent-scale.md").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
