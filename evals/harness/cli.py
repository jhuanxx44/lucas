import argparse
import asyncio
import json
from pathlib import Path

from evals.harness.suite import run_suite
from evals.harness.validation import validate_task


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m evals.harness")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate-task", help="validate a task and its graders")
    validate.add_argument("task")
    validate.add_argument("--runs-root", default="runs")
    suite = subparsers.add_parser("run-suite", help="run a suite and write a summary")
    suite.add_argument("suite")
    suite.add_argument("--agent", default="oracle")
    suite.add_argument("--trials", type=int, default=1)
    suite.add_argument("--runs-root", default="runs")
    args = parser.parse_args(argv)

    if args.command == "validate-task":
        result = asyncio.run(validate_task(args.task, Path(args.runs_root)))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.command == "run-suite":
        summary = asyncio.run(
            run_suite(args.suite, args.agent, args.trials, Path(args.runs_root))
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    return 1
