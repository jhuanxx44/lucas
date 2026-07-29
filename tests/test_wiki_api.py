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
    ws.ingested_root = "/tmp/test_ingested"
    ws.reports_root = "/tmp/test_reports"
    ws.memory_root = "/tmp/test_memory"
    ws.root = "/tmp/test_workspace"
    ws.user_id = "test"
    return ws


def test_wiki_index_returns_sections():
    ws = _ws_mock()
    client = _make_client(ws)
    resp = client.get("/api/wiki/index")
    assert resp.status_code == 200
    data = resp.json()
    assert "sections" in data


def test_wiki_page_not_found():
    ws = _ws_mock()
    client = _make_client(ws)
    resp = client.get("/api/wiki/nonexistent.md")
    assert resp.status_code == 404


def test_wiki_search_reports_removed_endpoint():
    ws = _ws_mock()
    client = _make_client(ws)
    resp = client.get("/api/wiki/search?q=电池")
    assert resp.status_code == 200
    data = resp.json()
    assert data == {
        "results": [],
        "note": "search_wiki endpoint removed; use /api/wiki/recall",
    }


def test_report_endpoint_reads_reports_root(tmp_path):
    reports_root = tmp_path / "reports"
    report_path = reports_root / "industry" / "report.md"
    report_path.parent.mkdir(parents=True)
    report_path.write_text(
        "---\ntitle: Test Report\n---\n\nReport body\n",
        encoding="utf-8",
    )
    ws = _ws_mock()
    ws.reports_root = str(reports_root)

    with patch("server.routers.wiki.LocalWorkspace", return_value=ws):
        from server.app import create_app

        response = TestClient(create_app()).get("/api/wiki/report/industry/report.md")

    assert response.status_code == 200
    assert response.json()["content"].strip() == "Report body"


def test_wiki_path_traversal_blocked():
    ws = _ws_mock()
    client = _make_client(ws)
    resp = client.get("/api/wiki/%2e%2e/requirements.txt")
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


def test_classify_source_returns_friendly_error():
    """classify 端点：service 构造或 LLM 调用失败 → 500 + 中文友好 detail（不是裸异常）"""
    ws = _ws_mock()
    with patch("server.routers.wiki.LocalWorkspace", return_value=ws), \
         patch("server.routers.wiki._create_knowledge_service",
               side_effect=RuntimeError("LLM 配置缺失")):
        from server.app import create_app
        resp = TestClient(create_app(), raise_server_exceptions=False).post(
            "/api/wiki/classify-source", json={"content": "材料内容"})

    assert resp.status_code == 500
    assert "分类失败" in resp.json()["detail"]


def test_ingest_source_init_failure_yields_error_event():
    """ingest 的 SSE 流内 service 构造失败 → 以 error 事件收尾，而不是断连"""
    ws = _ws_mock()
    with patch("server.routers.wiki.LocalWorkspace", return_value=ws), \
         patch("server.routers.wiki._create_knowledge_service",
               side_effect=RuntimeError("LLM 配置缺失")):
        from server.app import create_app
        resp = TestClient(create_app()).post(
            "/api/wiki/ingest-source",
            json={"content": "材料内容", "title": "t", "industry": "电子"})

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    assert "event: error" in resp.text
    assert "初始化知识服务失败" in resp.text
