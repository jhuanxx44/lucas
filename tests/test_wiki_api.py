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
    resp = client.get("/api/wiki/companies/300750-宁德时代.md")
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
