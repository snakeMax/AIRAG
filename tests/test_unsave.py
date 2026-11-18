"""Unsaving: out of My library, kept in History, restorable from Recently removed."""
from fastapi.testclient import TestClient

from airag import config, history, mylibrary, paths

REC = {"id": "unsave-abc123", "query": "ev sales norway", "title": "EV sales", "outcome": "article", "status": "done",
       "article": "# EV sales\n\nMost new cars are electric [1].", "created": "2026-11-18T10:00:00+01:00",
       "article_sources": [{"n": 1, "title": "OFV", "url": "https://ofv.no"}], "tags": ["ev"]}


def _client(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "LOCAL_DIR", tmp_path / "local")
    config.save({"library": {"personal_folder": str(tmp_path / "lib")}})
    from airag.main import app
    c = TestClient(app, base_url="http://127.0.0.1")
    c.get("/")
    return c


def test_unsave_keeps_history_and_restores(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    history.save(dict(REC), 50)
    r = c.post("/api/mylibrary/save", json={"id": REC["id"]})
    assert r.status_code == 200
    md = r.json()["path"]
    assert history.get(REC["id"])["saved_path"] == md
    assert [i["id"] for i in c.get("/api/mylibrary/saved").json()["items"]] == [REC["id"]]

    r = c.post("/api/mylibrary/unsave", json={"id": REC["id"]})
    assert r.status_code == 200
    assert c.get("/api/mylibrary/saved").json()["items"] == []
    assert history.get(REC["id"])["saved_path"] is None and history.get(REC["id"])["article"]   # still in History
    removed = c.get("/api/mylibrary/removed").json()["items"]
    assert len(removed) == 1 and removed[0]["title"] == "EV sales"

    r = c.post("/api/mylibrary/restore", json={"rid": removed[0]["rid"]})
    assert r.status_code == 200
    items = c.get("/api/mylibrary/saved").json()["items"]
    assert len(items) == 1 and items[0]["tags"] == ["ev"]
    assert history.get(REC["id"])["saved_path"] == r.json()["path"]
    assert c.get("/api/mylibrary/removed").json()["items"] == []
    assert not mylibrary.load_saved(config.load(), items[0]["file"])["edited_outside"]


def test_unsave_by_file_and_unknown(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    rec = dict(REC, id="unsave-def456")
    history.save(rec, 50)
    c.post("/api/mylibrary/save", json={"id": rec["id"]})
    f = c.get("/api/mylibrary/saved").json()["items"][0]["file"]
    history.delete(rec["id"])                                  # dropped out of History meanwhile
    assert c.post("/api/mylibrary/unsave", json={"files": [f, "../../etc/passwd"]}).status_code == 200
    assert history.get(rec["id"])["article"]                   # put back in History
    assert c.post("/api/mylibrary/unsave", json={"files": ["nope.airag.json"]}).status_code == 404
    assert c.post("/api/mylibrary/restore", json={"rid": "../x"}).status_code == 404
