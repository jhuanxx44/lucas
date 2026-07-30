from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
TARGETS = ["auth-gateway", "billing-worker", "notification-api"]


def _service(name):
    return yaml.safe_load((ROOT / "services" / name / "service.yaml").read_text())


def test_only_eligible_services_are_migrated_without_losing_business_config():
    for name in TARGETS:
        api = _service(name)["identity_api"]
        assert api == {
            "version": 2,
            "endpoint": "/v2/identity",
            "timeout_seconds": 8,
            "headers": {"X-Identity-Version": "2"},
        }

    assert _service("auth-gateway")["replicas"] == 3
    assert _service("billing-worker")["queue"] == "billing-events"
    assert _service("notification-api")["replicas"] == 2
    assert _service("catalog-api")["identity_api"]["version"] == 2
    assert _service("report-exporter")["identity_api"]["version"] == 1


def test_rollout_respects_dependencies_gates_and_reverse_rollback():
    text = (ROOT / "docs/generated/identity-v2-rollout.md").read_text()
    deploy = ["auth-gateway", "billing-worker", "notification-api"]
    rollback = list(reversed(deploy))

    deploy_positions = [text.index(name) for name in deploy]
    assert deploy_positions == sorted(deploy_positions)
    assert all(gate in text for gate in (
        "identity-v2 healthcheck",
        "billing reconciliation",
        "notification canary",
    ))
    folded = text.casefold()
    rollback_start = folded.find("rollback")
    if rollback_start < 0:
        rollback_start = text.index("回滚")
    rollback_section = text[rollback_start:]
    rollback_positions = [rollback_section.index(name) for name in rollback]
    assert rollback_positions == sorted(rollback_positions)
