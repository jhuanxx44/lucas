"""从 run trace 统计重读次数与压缩次数——Context 压缩实验的核心归因指标。

背景：2026-08-01 的压缩实验里，「压缩丢掉内容 → 模型重新读回来」这条因果链只能靠
人工翻 trace 才发现（PLAN-01 第 14–18 步重读 5 个 service.yaml）。本脚本把它变成
确定性可算的指标。

重读定义：同一 (tool, path) 的第 2 次及以后的调用。read_file 带 offset 时按
(path, offset) 区分——翻页读同一文件不算重读，重复读同一段才算。

用法：
    .venv/bin/python scripts/count_context_rereads.py runs/<run_id>
    .venv/bin/python scripts/count_context_rereads.py runs/<run_id> --json
    .venv/bin/python scripts/count_context_rereads.py 'runs/ctx-*'   # 汇总多个 run
"""
import argparse
import glob
import json
from collections import Counter
from pathlib import Path

READ_TOOLS = {"read_file", "list_files", "search"}


def analyze(trace_path: Path) -> dict:
    calls = Counter()          # (tool, key) -> 次数
    compressions = 0
    steps = 0
    total_tool_calls = 0
    order: list[tuple[str, str]] = []

    for line in trace_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        name = event.get("event")
        data = event.get("data", {}) or {}
        if name == "step_started":
            steps += 1
        elif name == "context_compressed":
            compressions += 1
        elif name == "tool_call_started":
            total_tool_calls += 1
            tool = data.get("tool", "?")
            if tool not in READ_TOOLS:
                continue
            args = data.get("args", {}) or {}
            path = args.get("path") or args.get("query") or ""
            key = str(path)
            if tool == "read_file" and args.get("offset"):
                key = f"{path}@{args['offset']}"
            calls[(tool, key)] += 1
            order.append((tool, key))

    repeated = {f"{tool}:{key}": count for (tool, key), count in calls.items() if count > 1}
    reread_count = sum(count - 1 for count in calls.values() if count > 1)
    return {
        "trace": str(trace_path),
        "steps": steps,
        "total_tool_calls": total_tool_calls,
        "read_calls": len(order),
        "distinct_read_targets": len(calls),
        "reread_count": reread_count,
        "compressions": compressions,
        "repeated_targets": dict(sorted(repeated.items(), key=lambda kv: -kv[1])),
    }


def _find_traces(pattern: str) -> list[Path]:
    matches = [Path(p) for p in sorted(glob.glob(pattern))]
    traces = []
    for match in matches:
        if match.is_file() and match.name.endswith(".jsonl"):
            traces.append(match)
        elif match.is_dir() and (match / "trace.jsonl").is_file():
            traces.append(match / "trace.jsonl")
    return traces


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="run 目录、trace.jsonl，或 glob 模式")
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    args = parser.parse_args()

    traces = _find_traces(args.path)
    if not traces:
        print(f"未找到 trace: {args.path}")
        return 1

    results = [analyze(trace) for trace in traces]
    if args.json:
        print(json.dumps(results if len(results) > 1 else results[0],
                         ensure_ascii=False, indent=2))
        return 0

    for result in results:
        run = Path(result["trace"]).parent.name
        print(f"── {run}")
        print(f"   步数 {result['steps']}  工具调用 {result['total_tool_calls']}"
              f"  压缩 {result['compressions']} 次")
        print(f"   读取调用 {result['read_calls']} 次，覆盖 {result['distinct_read_targets']}"
              f" 个不同目标 → 重读 {result['reread_count']} 次")
        for target, count in result["repeated_targets"].items():
            print(f"     {count}× {target}")
    if len(results) > 1:
        print(f"\n合计 {len(results)} 个 run："
              f"重读 {sum(r['reread_count'] for r in results)} 次，"
              f"压缩 {sum(r['compressions'] for r in results)} 次")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
