from pathlib import Path
import re

import yaml


ROOT = Path(__file__).resolve().parents[1]


def _yaml(path):
    return yaml.safe_load((ROOT / path).read_text())


def test_only_evidence_backed_runbook_actions_are_applied():
    checkout = _yaml("services/checkout-api/config.yaml")
    assert checkout["payment_client"] == {
        "base_url": "https://payment.internal",
        "timeout_seconds": 6,
        "max_retries": 1,
    }
    assert checkout["concurrency"] == 24
    assert checkout["inventory_client"] == {
        "base_url": "https://inventory.internal",
        "timeout_seconds": 2,
    }

    worker = _yaml("services/order-worker/config.yaml")
    assert worker == {
        "service": "order-worker",
        "queue": "paid-orders",
        "concurrency": 12,
        "idempotency_key_required": True,
    }
    assert _yaml("services/inventory-api/config.yaml")["reservation_timeout_seconds"] == 2


def test_report_contains_timeline_evidence_changes_validation_and_rollback():
    text = (ROOT / "reports/INC-042.md").read_text()
    for required in (
        "09:40",
        "10:05",
        "evidence/metrics-2026-07-30.md",
        "evidence/deploy-timeline.md",
        "logs/checkout-api.log",
        "logs/order-worker.log",
        "11.2%",
        "4.8",
        "timeout_seconds",
        "idempotency_key_required",
        "inventory-api",
        "verify checkout-payment --window 10m",
        "verify payment-idempotency --samples 200",
    ):
        assert required in text

    heading = re.search(r"^##[^\n]*(?:rollback|回滚)", text, flags=re.IGNORECASE | re.MULTILINE)
    assert heading is not None
    rollback = text[heading.start():]
    assert rollback.index("order-worker") < rollback.index("checkout-api")
