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


def test_trash_and_restore_notes_and_folders(S):
    from airag.notes import store, pathguard
    v = store.create_vault(S, "T", "research")
    a = store.create_note(S, v, "Topics", "Moose", "x\n")
    store.create_note(S, v, "Topics/Sub", "Deer", "y\n")
    base = store.vault_dir(S, v)
    r = store.trash(S, v, a["path"])
    assert not (base / a["path"]).exists() and (base / r["trashed"]).read_text(encoding="utf-8").endswith("x\n")
    assert r["trashed"].startswith(".trash/")
    store.create_note(S, v, "Topics", "Moose", "again\n")
    r2 = store.trash(S, v, "Topics/Moose.md")
    assert r2["trashed"] != r["trashed"]                                   # never overwrites the trash
    store.restore(S, v, r2["trashed"], "Topics/Moose.md")
    assert (base / ".trash" / "Topics").exists()                          # the first trashed Moose is still there
    assert (base / "Topics/Moose.md").read_text(encoding="utf-8").endswith("again\n")
    with pytest.raises(store.NotesError):
        store.restore(S, v, r["trashed"], "Topics/Moose.md")               # place taken
    f = store.trash(S, v, "Topics/Sub", folder=True)
    assert (base / f["trashed"] / "Deer.md").exists() and not (base / "Topics/Sub").exists()
    for bad in ["", ".", "../x.md", ".obsidian/app.json"]:
        with pytest.raises((store.NotesError, pathguard.PathError)):
            store.trash(S, v, bad, folder=True)
    with pytest.raises((store.NotesError, pathguard.PathError)):
        store.restore(S, v, "Topics/Moose.md", "Elsewhere.md")             # only from .trash


def test_restore_tidies_empty_trash_folders(S):
    from airag.notes import store
    v = store.create_vault(S, "T2", "empty")
    store.create_note(S, v, "A/B", "N", "x")
    base = store.vault_dir(S, v)
    r = store.trash(S, v, "A/B/N.md")
    store.restore(S, v, r["trashed"], r["path"])
    assert not (base / ".trash" / "A").exists()


def test_move_notes_and_folders_updates_path_links(S):
    from airag.notes import store, move, pathguard
    v = store.create_vault(S, "M", "empty")
    store.create_note(S, v, "Topics", "Moose", "x")
    store.create_note(S, v, "Topics/Deep", "Deer", "y")
    store.create_note(S, v, "Archive", "Keep", "z")
    store.write_note(S, v, "Index.md", "[[Moose]] [[Topics/Moose#Facts|m]] ![[Topics/Moose]] [a](Topics/Moose.md) "
                     "[d](Topics/Deep/Deer.md) [[Topics/Deep/Deer]] [w](https://x.org/Topics/Moose.md)")
    base = store.vault_dir(S, v)
    r = move.move(S, v, "Topics/Moose.md", "Archive")
    assert r["path"] == "Archive/Moose.md" and (base / "Archive/Moose.md").exists() and r["links"] == 1
    t = store.read_note(S, v, "Index.md")
    assert "[[Moose]]" in t and "[[Archive/Moose#Facts|m]]" in t and "![[Archive/Moose]]" in t and "](Archive/Moose.md)" in t
    assert "https://x.org/Topics/Moose.md" in t                              # web links untouched
    r = move.move(S, v, "Topics/Deep", "Archive", folder=True)
    t = store.read_note(S, v, "Index.md")
    assert (base / "Archive/Deep/Deer.md").exists() and "[[Archive/Deep/Deer]]" in t and "](Archive/Deep/Deer.md)" in t
    with pytest.raises(store.NotesError):
        move.move(S, v, "Archive", "Archive/Deep", folder=True)            # into itself
    store.create_note(S, v, "", "Keep", "top")
    with pytest.raises(store.NotesError):
        move.move(S, v, "Archive/Keep.md", "")                             # name taken at the top
    with pytest.raises((store.NotesError, pathguard.PathError)):
        move.move(S, v, "Archive/Keep.md", "../outside")
    assert move.move(S, v, "Archive/Moose.md", "")["path"] == "Moose.md"
