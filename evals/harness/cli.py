import argparse
import asyncio
import json
from pathlib import Path

from evals.harness.validation import validate_task


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m evals.harness")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate-task", help="validate a task and its graders")
    validate.add_argument("task")
    validate.add_argument("--runs-root", default="runs")
    args = parser.parse_args(argv)

    if args.command == "validate-task":
        result = asyncio.run(validate_task(args.task, Path(args.runs_root)))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    return 1
