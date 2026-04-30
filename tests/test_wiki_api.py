import os

import pytest
from unittest.mock import patch, MagicMock
from fastapi import HTTPException
from fastapi.testclient import TestClient

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))


def _make_client(ws_mock):
    with patch("server.routers.wiki.LocalWorkspace", return_value=ws_mock):
        from server.app import create_app
        app = create_app()
        return TestClient(app)


def _ws_mock(wiki_root=None, raw_root=None):
    ws = MagicMock()
    ws.wiki_root = wiki_root or os.path.join(PROJECT_ROOT, "wiki")
    ws.raw_root = raw_root or os.path.join(PROJECT_ROOT, "raw")
    ws.memory_root = "/tmp/test_memory"
    ws.root = "/tmp/test_workspace"
    ws.user_id = "test"
    return ws


def test_wiki_index_returns_sections():
    ws = _ws_mock()
    client = _make_client(ws)
    resp = client.get("/api/wiki/index", headers={"X-User-Id": "test"})
    assert resp.status_code == 200
    data = resp.json()
    assert "sections" in data


def test_wiki_page_not_found():
    ws = _ws_mock()
    client = _make_client(ws)
    resp = client.get("/api/wiki/nonexistent.md", headers={"X-User-Id": "test"})
    assert resp.status_code == 404


def test_wiki_search():
    ws = _ws_mock()
    client = _make_client(ws)
    resp = client.get("/api/wiki/search?q=电池", headers={"X-User-Id": "test"})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


def test_wiki_path_traversal_blocked():
    ws = _ws_mock()
    client = _make_client(ws)
    resp = client.get("/api/wiki/%2e%2e/requirements.txt", headers={"X-User-Id": "test"})
    assert resp.status_code in (403, 404)


def test_safe_join_rejects_traversal():
    from server.routers.wiki import _safe_join
    with pytest.raises(HTTPException) as exc_info:
        _safe_join("/tmp/wiki", "../../etc/passwd")
    assert exc_info.value.status_code == 403


def test_safe_join_rejects_base():
    from server.routers.wiki import _safe_join
    with pytest.raises(HTTPException) as exc_info:
        _safe_join("/tmp/wiki", "")
    assert exc_info.value.status_code == 403
