import pytest

from tests import mock

mock.install(settings_patch=False)


@pytest.fixture
def S(tmp_path):
    return {"notes": {"root": str(tmp_path / "Notes"), "main": ""}}


def test_linked_obsidian_vault_is_writable_unless_read_only(S, tmp_path):
    from airag.notes import store
    ob = tmp_path / "MyObsidian"
    (ob / ".obsidian").mkdir(parents=True)
    (ob / "Old.md").write_text("old\n", encoding="utf-8")
    v = store.link_vault(S, str(ob))
    r = store.create_note(S, v, "", "From AIRAG", "hello\n")
    assert (ob / r["path"]).read_text(encoding="utf-8").endswith("hello\n")
    old = store.read_note(S, v, "Old.md")
    import hashlib
    h = hashlib.sha256(old.encode()).hexdigest()
    (ob / "Old.md").write_text("changed in Obsidian\n", encoding="utf-8")     # Obsidian edits meanwhile
    with pytest.raises(store.NotesError):
        store.write_note(S, v, "Old.md", "mine\n", expected_hash=h)
    assert (ob / "Old.md").read_text(encoding="utf-8") == "changed in Obsidian\n"
    store.set_access(S, v["id"], False)
    v = store.get_vault(S, v["id"])
    with pytest.raises(store.NotesError):
        store.create_note(S, v, "", "Nope", "x")
    assert store.vaults(S)[0]["read_only"] is True
    assert not any(p.name == "index.db" for p in ob.rglob("*"))           # AIRAG's index lives outside the vault


def test_main_vault_api(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from airag import config
    from airag.main import app
    real = config.load

    def save(patch, *a, **k):
        for k, v in patch.items():
            S2.setdefault(k, {}).update(v)
        return S2
    mock.install()
    S2 = {**real(), "notes": {"root": str(tmp_path / "Notes"), "main": ""}}
    monkeypatch.setattr(config, "load", lambda *a, **k: S2)
    monkeypatch.setattr(config, "save", save)
    from airag.notes import api as napi
    monkeypatch.setattr(napi.config, "load", lambda *a, **k: S2)
    monkeypatch.setattr(napi.config, "save", save)
    c = TestClient(app, base_url="http://127.0.0.1")
    c.get("/")
    hdr = {}
    a = c.post("/api/notes/vaults", json={"name": "First", "template": "empty"}, headers=hdr).json()
    assert S2["notes"]["main"] == a["id"]                                   # first vault becomes main
    ob = tmp_path / "Ob"; ob.mkdir()
    b = c.post("/api/notes/vaults/link", json={"folder": str(ob), "main": True}, headers=hdr).json()
    assert S2["notes"]["main"] == b["id"]
    r = c.get("/api/notes/vaults", headers=hdr).json()
    assert r["main"] == b["id"] and [v["main"] for v in r["vaults"]] == [False, True]
    c.post("/api/notes/main", json={"vid": a["id"]}, headers=hdr)
    assert S2["notes"]["main"] == a["id"]
    c.delete(f"/api/notes/vaults/{a['id']}", headers=hdr)
    assert S2["notes"]["main"] == b["id"]                                   # removing the main one picks another


def test_obsidian_link_is_built_from_the_vault_path():
    from pathlib import Path
    from airag.notes import obsidian
    u = obsidian.uri_for(Path("/home/me/My vault/a&b.md"))
    assert u == "obsidian://open?path=%2Fhome%2Fme%2FMy%20vault%2Fa%26b.md"
