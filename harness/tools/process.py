import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from harness.tools.base import ToolResult, ToolSpec

MAX_OUTPUT_CHARS = 8000


def make_run_tests_spec(default_timeout: float = 60.0) -> ToolSpec:
    def run_tests(workspace: Path, args: dict) -> ToolResult:
        command = args.get("command")
        if not isinstance(command, list) or not command or any(
            not isinstance(item, str) for item in command
        ):
            return ToolResult(status="invalid_input", error_code="bad_args",
                              observation="command must be a non-empty list of strings")
        if command[0] != "pytest":
            return ToolResult(status="denied", error_code="command_not_allowed",
                              observation="only commands starting with 'pytest' are allowed")
        timeout = args.get("timeout", default_timeout)
        if not isinstance(timeout, (int, float)) or timeout <= 0:
            timeout = default_timeout
        argv = [sys.executable, "-m", "pytest", *command[1:]]
        if "-p" not in argv:
            argv.extend(["-p", "no:cacheprovider"])
        env = {"PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1"}
        start = time.monotonic()
        process = subprocess.Popen(
            argv,
            cwd=workspace,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        try:
            output, _ = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            process.wait()
            return ToolResult(
                status="timeout", error_code="timeout",
                observation=f"pytest timed out after {timeout}s and was killed",
                duration_ms=(time.monotonic() - start) * 1000,
            )
        duration_ms = (time.monotonic() - start) * 1000
        output = output or ""
        truncated = len(output) > MAX_OUTPUT_CHARS
        observation = (
            f"exit code: {process.returncode}\n" + output[-MAX_OUTPUT_CHARS:]
        )
        return ToolResult(
            status="ok",
            observation=observation,
            duration_ms=duration_ms,
            truncated=truncated,
        )

    return ToolSpec(
        name="run_tests",
        description="在工作区内运行 pytest（仅允许以 pytest 开头的命令）",
        args_description='{"command": ["pytest", ...], "timeout": 可选秒数，默认 60}',
        handler=run_tests,
    )
