import os
import time

import pytest

from agents.manager import Manager


def _manager(tmp_path, monkeypatch):
    manager = object.__new__(Manager)
    monkeypatch.setattr(manager, "_PENDING_DIR", str(tmp_path / "pending_ingest"))
    monkeypatch.setattr(manager, "_PENDING_PATH", str(tmp_path / "_pending_ingest.json"))
    return manager


def test_pending_ingest_uses_distinct_files(tmp_path, monkeypatch):
    manager = _manager(tmp_path, monkeypatch)

    first_id = manager._save_pending_ingest({"title": "first"})
    second_id = manager._save_pending_ingest({"title": "second"})

    first, first_status = manager._load_pending_ingest(first_id)
    assert first_status == "ok"
    assert first["title"] == "first"

    second_path = manager._pending_path(second_id)
    assert os.path.isfile(second_path)

    second, second_status = manager._load_pending_ingest(second_id)
    assert second_status == "ok"
    assert second["title"] == "second"


@pytest.mark.asyncio
async def test_dispatch_parses_pending_action_without_llm(tmp_path, monkeypatch):
    manager = _manager(tmp_path, monkeypatch)
    value = manager._pending_action_value("pending123", "新能源")

    action, payload = await manager._dispatch(value)

    assert action == "ingest_confirm"
    assert payload == {"pending_id": "pending123", "industry": "新能源"}


def test_pending_ingest_without_id_rejects_ambiguous_pending(tmp_path, monkeypatch):
    manager = _manager(tmp_path, monkeypatch)
    manager._save_pending_ingest({"title": "first"})
    manager._save_pending_ingest({"title": "second"})

    pending, status = manager._load_pending_ingest("")

    assert pending is None
    assert status == "ambiguous"


def test_pending_ingest_falls_back_to_legacy_singleton(tmp_path, monkeypatch):
    manager = _manager(tmp_path, monkeypatch)
    legacy_path = tmp_path / "_pending_ingest.json"
    legacy_path.write_text('{"title": "legacy"}', encoding="utf-8")

    pending, status = manager._load_pending_ingest("")

    assert status == "ok"
    assert pending["title"] == "legacy"
    assert not legacy_path.exists()


def test_pending_ingest_cleans_expired_files(tmp_path, monkeypatch):
    manager = _manager(tmp_path, monkeypatch)
    pending_id = manager._save_pending_ingest({"title": "old"})
    path = manager._pending_path(pending_id)
    old_time = time.time() - manager._PENDING_TTL_SECONDS - 60
    os.utime(path, (old_time, old_time))

    manager._cleanup_pending_ingest()

    assert not os.path.exists(path)
