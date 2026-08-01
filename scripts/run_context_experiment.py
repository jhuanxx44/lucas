#!/usr/bin/env python3
"""阶段 1 Context 压缩对照实验：跑三臂并生成对比报告。

用法:
  .venv/bin/python scripts/run_context_experiment.py [--trials 3] [--runs-root runs]

三臂（通过 LUCAS_CONTEXT_WINDOW 环境变量切换）:
  baseline : 0        —— 机制关闭，与旧行为逐字节一致
  prod     : 1000000  —— 生产窗口，预期不触发压缩（验证"现有任务不超预算"）
  trigger  : 20000    —— 缩小窗口使压缩真实触发，验证省 token 与成功率

报告写入 docs/experiments/2026-08-01-context-compression-v1.md，
运行日志追加 docs/experiments/experiment-log.md。
"""
import argparse
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUITE = ROOT / "evals" / "suites" / "context-compression-experiment.yaml"
REPORT = ROOT / "docs" / "experiments" / "2026-08-01-context-compression-v1.md"
LOG = ROOT / "docs" / "experiments" / "experiment-log.md"

ARMS = [
    ("baseline", "0"),
    ("prod", "1000000"),
    ("trigger", "20000"),
]


def run_suite(arm: str, window: str, trials: int, runs_root: Path) -> Path:
    env = {**os.environ, "LUCAS_CONTEXT_WINDOW": window}
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    arm_dir = runs_root / f"context-compression-{arm}-{stamp}-{uuid.uuid4().hex[:8]}"
    arm_dir.mkdir(parents=True, exist_ok=False)
    cmd = [
        sys.executable, "-m", "evals.harness", "run-suite",
        str(SUITE), "--agent", "lucas-single",
        "--trials", str(trials), "--runs-root", str(arm_dir),
    ]
    print(f"┌─ arm={arm} window={window} trials={trials}")
    result = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stdout[-2000:])
        print(result.stderr[-2000:])
        raise SystemExit(f"arm {arm} failed")
    summary = json.loads((arm_dir / "summary.json").read_text(encoding="utf-8"))
    print(f"└─ arm={arm} success_rate={summary['success_rate']} "
          f"runs={summary['runs_total']}")
    return arm_dir


def trace_stats(run_dir: Path) -> dict:
    """从单 run trace 汇总：prompt_tokens、步数、压缩事件。"""
    prompt_tokens = 0
    steps = 0
    compressions = 0
    freed_tokens = 0
    dropped_steps = 0
    path = run_dir / "trace.jsonl"
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            event = json.loads(line)
            name = event["event"]
            data = event.get("data", {})
            if name == "model_call_finished":
                prompt_tokens += int(data.get("prompt_tokens", 0))
            elif name == "step_started":
                steps += 1
            elif name == "context_compressed":
                compressions += 1
                freed_tokens += int(data.get("freed_tokens", 0))
                dropped_steps += len(data.get("dropped_steps", []))
    return {
        "prompt_tokens": prompt_tokens,
        "steps": steps,
        "compressions": compressions,
        "freed_tokens": freed_tokens,
        "dropped_steps": dropped_steps,
    }


def aggregate(arm_dir: Path) -> dict:
    summary = json.loads((arm_dir / "summary.json").read_text(encoding="utf-8"))
    per_task: dict[str, list[dict]] = {}
    for run in summary["runs"]:
        task = run["task_id"]
        stats = trace_stats(Path(arm_dir) / run["run_dir"].replace(f"{arm_dir}/", "", 1))
        per_task.setdefault(task, []).append({
            "success": run["success"],
            "cost_usd": run["cost_usd"],
            **stats,
        })
    return {
        "success_rate": summary["success_rate"],
        "by_task": {
            task: {
                "trials": len(runs),
                "passed": sum(1 for r in runs if r["success"]),
                "avg_prompt_tokens": round(sum(r["prompt_tokens"] for r in runs) / len(runs)),
                "avg_cost_usd": round(sum(r["cost_usd"] for r in runs) / len(runs), 6),
                "avg_steps": round(sum(r["steps"] for r in runs) / len(runs), 1),
                "compressions": sum(r["compressions"] for r in runs),
                "avg_freed_tokens": round(sum(r["freed_tokens"] for r in runs) / len(runs)),
            }
            for task, runs in per_task.items()
        },
    }


def write_report(arms: dict[str, dict], trials: int) -> None:
    baseline = arms["baseline"]
    trigger = arms["trigger"]
    rows = []
    for task in baseline["by_task"]:
        b = baseline["by_task"][task]
        t = trigger["by_task"].get(task, {})
        rows.append({
            "task": task,
            "base_pass": f"{b['passed']}/{b['trials']}",
            "trig_pass": f"{t.get('passed', 0)}/{t.get('trials', 0)}",
            "base_tokens": b["avg_prompt_tokens"],
            "trig_tokens": t.get("avg_prompt_tokens", 0),
            "delta": round((t.get("avg_prompt_tokens", 0) - b["avg_prompt_tokens"]) / max(1, b["avg_prompt_tokens"]) * 100, 1),
            "base_cost": b["avg_cost_usd"],
            "trig_cost": t.get("avg_cost_usd", 0),
            "base_steps": b["avg_steps"],
            "trig_steps": t.get("avg_steps", 0),
            "compressions": t.get("compressions", 0),
            "avg_freed": t.get("avg_freed_tokens", 0),
        })
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        "# 阶段 1：Context 压缩对照实验（baseline vs prod vs trigger）",
        "",
        f"日期：{now}",
        "对照固定项：同一 Runner、`deepseek-v4-flash`、temperature=0、固定 prompt 哈希、",
        "同一 task/grader 与预算；每档每题 ≥3 trials。",
        "",
        "## 方法",
        "",
        f"- baseline：`LUCAS_CONTEXT_WINDOW=0`（机制关闭，提交内容与旧行为逐字节一致）",
        "- prod：`LUCAS_CONTEXT_WINDOW=1000000`（生产窗口；预期不触发压缩）",
        "- trigger：`LUCAS_CONTEXT_WINDOW=20000`（真实输入最大约 14K（PLAN-01 单轮），",
        "  使压缩在长任务中段真实触发；预留输出按窗口 10% 缩放）",
        f"- 每档每题 {trials} trials，交错运行",
        "- 指标：success_rate / prompt_tokens（trace 汇总）/ cost / steps / 压缩次数",
        "",
        "## 结果",
        "",
        "| 任务 | baseline 通过 | trigger 通过 | baseline prompt | trigger prompt | Δ% | baseline cost | trigger cost | steps (base→tri) | 压缩次数 | 平均释放 token |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['task']} | {r['base_pass']} | {r['trig_pass']} | {r['base_tokens']} | "
            f"{r['trig_tokens']} | {r['delta']}% | {r['base_cost']} | {r['trig_cost']} | "
            f"{r['base_steps']}→{r['trig_steps']} | {r['compressions']} | {r['avg_freed']} |"
        )
    total_b = sum(r["base_tokens"] for r in rows)
    total_t = sum(r["trig_tokens"] for r in rows)
    delta = round((total_t - total_b) / max(1, total_b) * 100, 1)
    lines += [
        "",
        f"**合计：prompt_tokens {total_b} → {total_t}（{delta}%）**",
        "",
        "## 结论（决策门）",
        "",
        "- prompt_tokens 显著下降（≥20%）且成功率不降 → 达标即停，保留简单压缩实现",
        "- 成功率下降 → 提高窗口阈值或保留更多最近步骤，或放弃并记录失败案例",
        "- prod 臂未触发压缩 → 说明现有任务在真实 1M 窗口下不超预算，符合 5.1 决策门预期；",
        "  是否补 CTX 候选任务由本实验的 trigger 臂结果决定",
        "",
        "结论：待按上表数据填写（保留 / 缩小范围 / 删除）。",
        "",
        "## 失败样本",
        "",
        "待按失败 run 的 trace 填写。",
    ]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"报告已写入 {REPORT.relative_to(ROOT)}")


def append_log(arms: dict[str, dict]) -> None:
    entry = (
        "\n---\n\n"
        "## 2026-08-01：阶段 1 Context 压缩对照实验\n\n"
        "- 三臂结果：baseline success_rate="
        f"{arms['baseline']['success_rate']}，prod="
        f"{arms['prod']['success_rate']}，trigger="
        f"{arms['trigger']['success_rate']}\n"
        "- 报告：`docs/experiments/2026-08-01-context-compression-v1.md`\n"
        "- 决策：见报告结论\n"
    )
    with LOG.open("a", encoding="utf-8") as f:
        f.write(entry)
    print(f"日志已追加 {LOG.relative_to(ROOT)}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--runs-root", default=str(ROOT / "runs"))
    args = parser.parse_args()
    if args.trials < 3:
        print("warning: 建议 trials >= 3（计划要求每档每题 >= 3 trials）")
    runs_root = Path(args.runs_root)
    runs_root.mkdir(parents=True, exist_ok=True)
    arms: dict[str, dict] = {}
    for arm, window in ARMS:
        arm_dir = run_suite(arm, window, args.trials, runs_root)
        arms[arm] = aggregate(arm_dir)
    write_report(arms, args.trials)
    append_log(arms)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
