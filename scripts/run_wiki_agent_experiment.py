#!/usr/bin/env python3
"""在物化 Wiki 子库上运行生产子串 BM25 与可部署 jieba TF-IDF Agent 多 trial。"""
from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import statistics
import sys
import tempfile
import time
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RETRIEVER_DIR = ROOT / "evals/components/RETRIEVAL-BM25"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(RETRIEVER_DIR))

from evals.harness.adapters.lucas_single import LucasSingleAgent
from evals.harness.models import RunLimits, TaskSpec
from evals.harness.runner import run_trial
from harness.tools.base import ToolResult, ToolSpec
from utils.path_safety import resolve_within
from utils.wiki_core import _read_page
from scripts.wiki_corpus_common import materialize_manifest
from retriever import TFIDFRetriever, load_documents


DEFAULT_CORPUS = ROOT / "evals/corpora/wiki-scale-v1"
SIZES = (50, 200, 500)
TRIALS = 3
TASKS = {
    "QS-023": {
        "fact_groups": [["DDR4"], ["DDR5"], ["低功耗記憶體", "低功耗记忆体", "低功耗DRAM", "LPDDR"]],
        "evidence_paths": ["companies/半导体/南亞科技.md"],
    },
    "QS-029": {
        "fact_groups": [["1980"], ["1995"]],
        "evidence_paths": ["companies/食品饮料/奥德瓦拉.md", "companies/半导体/南亞科技.md"],
    },
    "QS-059": {
        "fact_groups": [["1998"], ["1999"]],
        "evidence_paths": ["companies/互联网/Google.md", "concepts/半导体/Athlon.md"],
    },
}


def tfidf_wiki_recall(workspace: Path, args: dict) -> ToolResult:
    query = args.get("query")
    if not isinstance(query, str) or not query.strip():
        return ToolResult(status="invalid_input", error_code="bad_args", observation="query must be a non-empty string")
    workspace_root = workspace.resolve()
    candidate = workspace_root / "wiki"
    if not candidate.exists() and not candidate.is_symlink():
        return ToolResult(status="ok", observation="（wiki 知识库为空，没有可召回的页面）")
    wiki_root = resolve_within(workspace_root, candidate, strict=True)
    if wiki_root is None or not wiki_root.is_dir():
        return ToolResult(status="denied", error_code="path_escape", observation="wiki root escapes workspace")
    paths, tokens, _ = load_documents(str(wiki_root))
    retriever = TFIDFRetriever(paths, tokens)
    # 查询与文档必须共享 tokenizer；LLM 给出的关键词可以是“南亚科技”这类复合短语。
    ranked = [(path, score) for path, score in retriever.search(query, 20) if score > 0]
    if not ranked:
        return ToolResult(status="ok", observation=f"知识库中没有与「{query.strip()}」相关的页面")
    parts = []
    for path, score in ranked:
        page = _read_page(str(wiki_root), path, 500)
        if page is None:
            continue
        name = Path(path).stem
        label = "摘要：" if page.get("source") == "summary" else ""
        body = label + page["content"] + ("\n…[truncated]" if page["truncated"] else "")
        parts.append(f"--- {name}（{path}） ---\n{body}")
    return ToolResult(status="ok", observation="\n\n".join(parts))


TFIDF_WIKI_RECALL_SPEC = ToolSpec(
    name="wiki_recall",
    description="从本地 wiki 知识库召回相关页面（TF-IDF 相关性排序）。"
                "query 应为预分词关键词（空格、逗号或顿号分隔），返回标题、路径和摘要。",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "minLength": 1,
                "description": "预分词关键词，以空格、逗号或顿号分隔",
            },
        },
        "required": ["query"],
        "additionalProperties": False,
    },
    handler=tfidf_wiki_recall,
)


def _task_spec(task_dir: Path, query: dict, task_id: str) -> TaskSpec:
    expected = {"query_id": task_id, **TASKS[task_id]}
    instruction = (
        f"请只使用 wiki_recall 回答：{query['query']}\n"
        "不要修改文件。返回 JSON，且只包含 query_id、facts、evidence_paths 三个字段。"
        f"query_id 固定为 {task_id}；facts 按问题顺序列出最短答案；"
        "evidence_paths 按 facts 对应顺序列出直接证据页面路径，不重复路径。"
    )
    return TaskSpec(
        id=task_id, title=query["query"], instruction=instruction, fixture="fixture",
        allowed_tools=["wiki_recall"], limits=RunLimits(max_steps=3, timeout_seconds=90, max_cost_usd=0),
        outcome_graders=[{"type": "answer_facts", **expected, "required": True}],
        safety_graders=[{"type": "forbidden_diff", "paths": ["**"], "required": True}],
        process_graders=[
            {"type": "allowed_tools", "tools": ["wiki_recall"], "required": True},
            {"type": "max_steps", "value": 3, "required": True},
            {"type": "max_tool_calls", "value": 2, "required": True},
        ], tags=["retrieval-scale", "agent-outcome"], task_dir=task_dir,
    )


def score_answer(task_id: str, answer: object) -> dict:
    expected = TASKS[task_id]
    if not isinstance(answer, dict):
        return {"outcome_passed": False, "fact_coverage": 0.0, "evidence_coverage": 0.0,
                "unsupported_evidence": False}
    facts_text = "\n".join(str(value) for value in answer.get("facts", [])).casefold()
    groups = expected["fact_groups"]
    covered = sum(
        any(str(option).casefold() in facts_text for option in options)
        for options in groups
    )
    normalize = lambda value: str(value).removeprefix("wiki/")
    actual_paths = {
        normalize(path) for path in answer.get("evidence_paths", [])
        if isinstance(path, str) and path
    }
    expected_paths = {normalize(path) for path in expected["evidence_paths"]}
    evidence_covered = len(actual_paths & expected_paths)
    query_ok = answer.get("query_id") == task_id
    outcome = query_ok and covered == len(groups) and actual_paths == expected_paths
    return {
        "outcome_passed": outcome,
        "fact_coverage": covered / len(groups),
        "evidence_coverage": evidence_covered / len(expected_paths),
        "unsupported_evidence": bool(actual_paths - expected_paths),
    }


async def run_experiment(corpus_root: Path, trials: int) -> dict:
    master = corpus_root / "master/wiki"
    queries = {row["id"]: row for row in json.loads((corpus_root / "queries/test.json").read_text(encoding="utf-8"))["queries"]}
    runs_root = corpus_root / "results/agent-runs"
    runs_root.mkdir(parents=True, exist_ok=True)
    rows = []
    for task_id in TASKS:
        for size in SIZES:
            # 固定 seed-1；Agent 重复 trial 只测模型稳定性，不改变子库。
            manifest_path = corpus_root / f"manifests/controlled/{task_id}/seed-1/n{size:04d}.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            for retriever_name, spec in (("substr_bm25", None), ("jieba_tfidf", TFIDF_WIKI_RECALL_SPEC)):
                for trial_index in range(trials):
                    temp_root = Path(tempfile.mkdtemp(prefix="lucas-retrieval-scale-")).resolve()
                    try:
                        fixture = temp_root / "fixture"
                        reference = temp_root / "reference"
                        reference.mkdir(parents=True)
                        materialized = materialize_manifest(master, manifest_path, fixture / "wiki")
                        if materialized["documents_sha256"] != manifest["documents_sha256"]:
                            raise ValueError("materialized workspace hash does not match manifest")
                        task = _task_spec(temp_root, queries[task_id], task_id)
                        adapter = LucasSingleAgent(
                            wiki_recall_spec=spec,
                            variant=f"lucas-single-{retriever_name}",
                        )
                        started = time.perf_counter()
                        result, grade, run_dir = await run_trial(task, adapter, runs_root, trial_index)
                        elapsed = time.perf_counter() - started
                        run_manifest_path = run_dir / "manifest.json"
                        run_manifest = json.loads(run_manifest_path.read_text(encoding="utf-8"))
                        run_manifest.update({
                            "retriever": retriever_name, "size": size,
                            "corpus_manifest": manifest_path.relative_to(corpus_root).as_posix(),
                            "corpus_manifest_sha256": manifest["documents_sha256"],
                        })
                        run_manifest_path.write_text(json.dumps(run_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
                        trace_events = [json.loads(line) for line in (run_dir / "trace.jsonl").read_text(encoding="utf-8").splitlines()]
                        rows.append({
                            "task_id": task_id, "retriever": retriever_name, "size": size,
                            "trial": trial_index,
                            "original_harness_success": grade.success,
                            **score_answer(task_id, result.answer),
                            "success": score_answer(task_id, result.answer)["outcome_passed"]
                            and grade.safety_passed and grade.process_passed,
                            "finish_reason": result.finish_reason, "error": result.error,
                            "answer": result.answer, "steps": sum(e["event"] == "step_started" for e in trace_events),
                            "tool_calls": sum(e["event"] == "tool_call_started" for e in trace_events),
                            "prompt_tokens": getattr(result.usage, "prompt_tokens", 0) if result.usage else 0,
                            "completion_tokens": getattr(result.usage, "completion_tokens", 0) if result.usage else 0,
                            "cost_usd": result.cost_usd, "latency_seconds": round(elapsed, 4),
                            "run_dir": run_dir.relative_to(corpus_root).as_posix(),
                        })
                    finally:
                        shutil.rmtree(temp_root, ignore_errors=True)
                    print(f"[{task_id} n={size} {retriever_name} t={trial_index}] success={rows[-1]['success']}", flush=True)
    aggregates = []
    for task_id in TASKS:
        for size in SIZES:
            for retriever in ("substr_bm25", "jieba_tfidf"):
                values = [row for row in rows if row["task_id"] == task_id and row["size"] == size and row["retriever"] == retriever]
                aggregates.append({
                    "task_id": task_id, "size": size, "retriever": retriever,
                    "trials": len(values), "success_rate": statistics.fmean(row["success"] for row in values),
                    "fact_coverage_mean": statistics.fmean(row["fact_coverage"] for row in values),
                    "evidence_coverage_mean": statistics.fmean(row["evidence_coverage"] for row in values),
                    "unsupported_evidence_rate": statistics.fmean(row["unsupported_evidence"] for row in values),
                    "steps_mean": statistics.fmean(row["steps"] for row in values),
                    "tool_calls_mean": statistics.fmean(row["tool_calls"] for row in values),
                    "tokens_mean": statistics.fmean(row["prompt_tokens"] + row["completion_tokens"] for row in values),
                    "cost_usd_mean": statistics.fmean(row["cost_usd"] for row in values),
                    "latency_seconds_mean": statistics.fmean(row["latency_seconds"] for row in values),
                })
    return {
        "protocol": {"tasks": list(TASKS), "sizes": list(SIZES), "trials": trials, "seed": 1},
        "aggregates": aggregates, "rows": rows,
    }


def render_report(result: dict) -> str:
    lines = ["# Wiki Agent 多 trial 结果", "", "每个条件固定 controlled seed-1，成功率由确定性事实覆盖与证据路径 grader 判定。", "", "| Task | 规模 | 子串 BM25 | jieba TF-IDF |", "|---|---:|---:|---:|"]
    lookup = {(row["task_id"], row["size"], row["retriever"]): row for row in result["aggregates"]}
    for task_id in TASKS:
        for size in SIZES:
            left = lookup[(task_id, size, "substr_bm25")]["success_rate"]
            right = lookup[(task_id, size, "jieba_tfidf")]["success_rate"]
            lines.append(f"| {task_id} | {size} | {left:.3f} | {right:.3f} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus-root", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--trials", type=int, default=TRIALS)
    args = parser.parse_args()
    result = asyncio.run(run_experiment(args.corpus_root, args.trials))
    output_dir = args.corpus_root / "results"
    (output_dir / "agent-scale.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    report = render_report(result)
    (output_dir / "agent-scale.md").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
