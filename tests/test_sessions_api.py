from fastapi.testclient import TestClient

from server.routers.sessions import get_session_store
from server.services.session_store import SessionStore


def _client(tmp_path):
    from server.app import create_app

    app = create_app()
    app.dependency_overrides[get_session_store] = lambda: SessionStore(str(tmp_path))
    return TestClient(app)


def test_session_lifecycle_and_auto_title(tmp_path):
    client = _client(tmp_path)

    created = client.post("/api/sessions", json={}).json()
    session_id = created["id"]
    assert created["title"] == "新对话"

    messages = [
        {"id": "user-1", "role": "user", "content": "分析宁德时代的竞争优势"},
        {"id": "assistant-1", "role": "assistant", "content": "核心优势包括规模与技术。"},
    ]
    updated = client.put(
        f"/api/sessions/{session_id}/messages",
        json={"messages": messages},
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "分析宁德时代的竞争优势"

    detail = client.get(f"/api/sessions/{session_id}").json()
    assert detail["messages"] == messages

    sessions = client.get("/api/sessions").json()
    assert sessions[0]["id"] == session_id
    assert sessions[0]["message_count"] == 2

    renamed = client.patch(
        f"/api/sessions/{session_id}",
        json={"title": "宁德时代研究"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "宁德时代研究"

    deleted = client.delete(f"/api/sessions/{session_id}")
    assert deleted.status_code == 204
    assert client.get(f"/api/sessions/{session_id}").status_code == 404


def test_sessions_are_sorted_by_latest_update(tmp_path):
    client = _client(tmp_path)
    first = client.post("/api/sessions", json={"title": "第一条"}).json()
    second = client.post("/api/sessions", json={"title": "第二条"}).json()

    client.patch(f"/api/sessions/{first['id']}", json={"title": "最近更新"})

    sessions = client.get("/api/sessions").json()
    assert [session["id"] for session in sessions] == [first["id"], second["id"]]


def test_session_rejects_invalid_id(tmp_path):
    client = _client(tmp_path)

    response = client.get("/api/sessions/not-a-session")

    assert response.status_code == 404
