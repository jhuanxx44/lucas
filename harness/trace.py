import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from harness.models import TraceEvent


class TraceRecorder:
    def __init__(self, path: Path, run_id: str):
        self.path = path
        self.run_id = run_id
        self.sequence = 0
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")

    def record(self, event: str, data: dict | None = None) -> TraceEvent:
        self.sequence += 1
        trace_event = TraceEvent(
            sequence=self.sequence,
            run_id=self.run_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            event=event,
            data=data or {},
        )
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(trace_event), ensure_ascii=False) + "\n")
        return trace_event


def read_trace(path: Path) -> list[dict]:
    events = []
    with path.open("r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, 1):
            try:
                value = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"invalid trace JSON on line {line_number}: {e}") from e
            if not isinstance(value, dict):
                raise ValueError(f"trace line {line_number} must be a JSON object")
            events.append(value)
    return events
