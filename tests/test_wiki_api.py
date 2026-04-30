import pytest
from fastapi.testclient import TestClient


def test_wiki_index_returns_sections(monkeypatch):
    from server.app import create_app
    import server.routers.wiki as wiki_mod
    import os
    wiki_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "wiki")
    monkeypatch.setattr(wiki_mod, "WIKI_DIR", wiki_dir)
    app = create_app()
    client = TestClient(app)
    resp = client.get("/api/wiki/index")
    assert resp.status_code == 200
    data = resp.json()
    assert "sections" in data
    assert len(data["sections"]) > 0


def test_wiki_page_returns_content(monkeypatch):
    from server.app import create_app
    import server.routers.wiki as wiki_mod
    import os
    wiki_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "wiki")
    monkeypatch.setattr(wiki_mod, "WIKI_DIR", wiki_dir)
    app = create_app()
    client = TestClient(app)
    resp = client.get("/api/wiki/companies/新能源/300750-宁德时代.md")
    assert resp.status_code == 200
    data = resp.json()
    assert "frontmatter" in data
    assert "content" in data
    assert data["frontmatter"]["type"] == "company"


def test_wiki_page_not_found(monkeypatch):
    from server.app import create_app
    import server.routers.wiki as wiki_mod
    import os
    wiki_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "wiki")
    monkeypatch.setattr(wiki_mod, "WIKI_DIR", wiki_dir)
    app = create_app()
    client = TestClient(app)
    resp = client.get("/api/wiki/nonexistent.md")
    assert resp.status_code == 404


def test_wiki_search(monkeypatch):
    from server.app import create_app
    import server.routers.wiki as wiki_mod
    import os
    wiki_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "wiki")
    monkeypatch.setattr(wiki_mod, "WIKI_DIR", wiki_dir)
    app = create_app()
    client = TestClient(app)
    resp = client.get("/api/wiki/search?q=电池")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


def test_wiki_path_traversal_blocked(monkeypatch):
    from server.app import create_app
    import server.routers.wiki as wiki_mod
    import os
    wiki_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "wiki")
    monkeypatch.setattr(wiki_mod, "WIKI_DIR", wiki_dir)
    app = create_app()
    client = TestClient(app)
    # Starlette 会规范化 ../，所以用 URL 编码绕过框架层测试后端防护
    resp = client.get("/api/wiki/%2e%2e/requirements.txt")
    assert resp.status_code in (403, 404)

    # 直接测试路由函数的防护逻辑
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        wiki_mod.get_page("../../etc/passwd")
    assert exc_info.value.status_code == 403


def test_raw_file_rejects_base_and_traversal(monkeypatch):
    import os
    from fastapi import HTTPException
    import server.routers.wiki as wiki_mod

    raw_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "raw")
    monkeypatch.setattr(wiki_mod, "RAW_DIR", raw_dir)

    with pytest.raises(HTTPException) as exc_info:
        wiki_mod.get_raw_file("")
    assert exc_info.value.status_code == 403

    with pytest.raises(HTTPException) as exc_info:
        wiki_mod.get_raw_file("../../requirements.txt")
    assert exc_info.value.status_code == 403


def test_wiki_move_rejects_non_markdown_and_hidden_paths(monkeypatch, tmp_path):
    from fastapi import HTTPException
    import server.routers.wiki as wiki_mod

    monkeypatch.setattr(wiki_mod, "WIKI_DIR", str(tmp_path))
    src = tmp_path / "source.md"
    src.write_text("# Source", encoding="utf-8")

    with pytest.raises(HTTPException) as exc_info:
        wiki_mod.wiki_move(wiki_mod.MoveRequest(src="source.md", dst="target.json"))
    assert exc_info.value.status_code == 400

    with pytest.raises(HTTPException) as exc_info:
        wiki_mod.wiki_move(wiki_mod.MoveRequest(src="source.md", dst=".hidden/target.md"))
    assert exc_info.value.status_code == 400
