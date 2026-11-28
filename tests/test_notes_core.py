import os

import pytest

from tests import mock

mock.install(settings_patch=False)


@pytest.fixture
def S(tmp_path):
    return {"notes": {"root": str(tmp_path / "Notes")}}


def test_pathguard_refuses_escapes(tmp_path):
    from airag.notes import pathguard
    root = tmp_path / "v"
    root.mkdir()
    for bad in ["../x.md", "/etc/passwd", "C:/Windows/x.md", "\\\\server\\share\\x.md", "a/../../x.md", "CON.md",
                "nul", "a./b.md", "x .md ", "a:b.md", "note\u202egpj.md", ".obsidian/app.json", ".airag/index.db", ""]:
        with pytest.raises(pathguard.PathError):
            pathguard.resolve(root, bad)
    assert pathguard.resolve(root, "Notes/Idea.md") == (root / "Notes" / "Idea.md").resolve()


def test_pathguard_refuses_symlink_out(tmp_path):
    from airag.notes import pathguard
    root, out = tmp_path / "v", tmp_path / "outside"
    root.mkdir(); out.mkdir()
    try:
        os.symlink(out, root / "link")
    except OSError:
        pytest.skip("no symlinks here")
    with pytest.raises(pathguard.PathError):
        pathguard.resolve(root, "link/x.md")


def test_parser_properties_sections_links_tags():
    from airag.notes import parser
    text = ("---\ntype: claim\ntags: [status/checked, roads]\nyear: 2019\naliases:\n  - fence study\n"
            "evil: !!python/object:os.system 'rm'\n---\n"
            "Intro with [[Moose and roads|hub]] and #moose.\n\n## Results\nCollisions fell [[E6 crash data#2019]].\n"
            "```\n[[not a link]] #notatag\n```\n![[chart.png]] [site](https://example.com) [local](Other%20note.md)\n")
    n = parser.parse(text, "Fences")
    assert n.props["type"] == "claim" and n.props["year"] == 2019 and n.props["aliases"] == ["fence study"]
    assert isinstance(n.props["evil"], str)                       # never evaluated
    assert [s.heading for s in n.sections] == ["", "Results"]
    targets = [(l.target, l.heading, l.embed, l.kind) for l in n.links]
    assert ("Moose and roads", "", False, "wiki") in targets and ("E6 crash data", "2019", False, "wiki") in targets
    assert ("chart.png", "", True, "wiki") in targets and ("Other note", "", False, "md") in targets
    assert not any(t[0] == "not a link" for t in targets)
    assert set(n.tags) == {"status/checked", "roads", "moose"}
    assert n.gist.startswith("Intro with hub and")


def test_vaults_notes_index_and_search(S):
    from airag.notes import store, index, search
    v = store.create_vault(S, "Moose research", "research", "Moose and roads")
    assert [x["name"] for x in store.vaults(S)] == ["Moose research"]
    with pytest.raises(store.NotesError):
        store.create_vault(S, "Moose research")
    store.create_note(S, v, "Notes", "Fences halve collisions", "Where fences met wildlife crossings, collisions fell by half [[E6 crash data]].\n\n## Costs\nEach crossing cost NOK 30 million.\n",
                      {"type": "claim", "tags": ["status/checked"], "year": 2019})
    store.create_note(S, v, "Sources", "E6 crash data", "Crash counts per month on the E6. Fences halve collisions is the main finding.\n", {"type": "source", "year": 2017})
    store.create_note(S, v, "Notes", "Deer whistles", "No evidence that whistles work for deer.\n", {"type": "claim"})
    r = index.update(S, v)
    assert r["notes"] == 3 and r["added"] == 3
    assert index.update(S, v)["added"] == 0                      # incremental: nothing changed
    res = search.run(S, v, "crossing")
    assert res["notes"] == 1 and res["groups"][0]["title"] == "Fences halve collisions"
    assert {s["heading"] for s in res["groups"][0]["sections"]} == {"", "Costs"}   # every matching section
    assert search.run(S, v, "type:source")["notes"] == 1
    assert search.run(S, v, "prop:year>2018")["notes"] == 1
    assert search.run(S, v, "tag:status")["notes"] == 1
    assert search.run(S, v, "collisions -crossings")["groups"][0]["title"] == "E6 crash data"
    assert search.run(S, v, "whistles OR crossing")["notes"] == 2
    assert search.run(S, v, '"fell by half"')["notes"] == 1
    assert search.run(S, v, "linksto:\"E6 crash data\"")["notes"] == 1
    assert search.run(S, v, "path:Sources")["notes"] == 1
    assert search.run(S, v, "regex:NOK \\d+")["notes"] == 1
    with pytest.raises(search.QueryError):
        search.run(S, v, "regex:(a+)+$")
    assert search.run(S, v, "'; DROP TABLE notes; --")["notes"] == 0          # just text
    assert index.stats(S, v)["notes"] == 3
    bl = index.backlinks(S, v, "Sources/E6 crash data.md")
    assert [x["title"] for x in bl["linked"]] == ["Fences halve collisions"]
    bl2 = index.backlinks(S, v, "Notes/Fences halve collisions.md")
    assert [x["title"] for x in bl2["unlinked"]] == ["E6 crash data"]        # mentioned but not linked


def test_writes_keep_versions_and_refuse_stale_and_linked(S, tmp_path):
    from airag.notes import store, parser
    v = store.create_vault(S, "W", "empty")
    r = store.write_note(S, v, "a.md", "one")
    store.write_note(S, v, "a.md", "two", expected_hash=r["hash"])
    with pytest.raises(store.NotesError):
        store.write_note(S, v, "a.md", "three", expected_hash=r["hash"])      # stale copy
    assert list((store.private_dir(S, v) / "versions").rglob("*.md"))
    ext = tmp_path / "Obsidian"
    ext.mkdir()
    (ext / "x.md").write_text("hi", encoding="utf-8")
    lv = store.link_vault(S, str(ext), write=False)
    with pytest.raises(store.NotesError):
        store.write_note(S, lv, "x.md", "changed")                         # read-only linked vault: needs approval
    assert (ext / "x.md").read_text(encoding="utf-8") == "hi"
    assert not (ext / ".airag").exists()                                # AIRAG's data stays outside linked vaults


def test_notes_api_roundtrip(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    mock.install()
    from airag import config
    from airag.main import app
    real = config.load
    monkeypatch.setattr(config, "load", lambda *a, **k: {**real(*a, **k), "notes": {"root": str(tmp_path / "N")}})
    with TestClient(app, base_url="http://127.0.0.1") as c:
        c.get("/")
        v = c.post("/api/notes/vaults", json={"name": "Lore", "template": "worldbuilding"}).json()
        assert c.get("/api/notes/vaults").json()["vaults"][0]["template"] == "worldbuilding"
        assert c.get(f"/api/notes/{v['id']}/tree").json()["items"] == []        # worldbuilding: no preset folders
        n = c.post(f"/api/notes/{v['id']}/new", json={"title": "Aria the smith", "body": "Lives in [[Emberfall]].", "props": {"type": "person"}}).json()
        got = c.get(f"/api/notes/{v['id']}/note", params={"path": n["path"]}).json()
        assert got["props"]["type"] == "person"
        assert c.put(f"/api/notes/{v['id']}/note", json={"path": n["path"], "text": got["text"] + "\nSmith.", "hash": got["hash"]}).status_code == 200
        assert c.put(f"/api/notes/{v['id']}/note", json={"path": n["path"], "text": "x", "hash": got["hash"]}).status_code == 409
        assert c.get(f"/api/notes/{v['id']}/search", params={"q": "smith"}).json()["notes"] == 1
        assert c.get(f"/api/notes/{v['id']}/note", params={"path": "../../etc/passwd"}).status_code == 400
        assert c.get(f"/api/notes/{v['id']}/links", params={"path": n["path"]}).json()["outgoing"][0]["exists"] is False


def test_notes_folder_defaults_to_documents_and_can_change(tmp_path, monkeypatch):
    from pathlib import Path
    from airag.notes import store
    assert store.default_root() == Path.home() / "Documents" / "AIRAG Notes"     # system drive, not D:
    assert store.status({})["custom"] is False
    s = {"notes": {"root": str(tmp_path / "Elsewhere")}}
    assert store.root(s) == tmp_path / "Elsewhere" and store.status(s)["custom"] is True


def test_tag_list_counts_nested_tags(S):
    from airag.notes import store, index
    v = store.create_vault(S, "T", "empty")
    store.create_note(S, v, "", "A", "#status/draft and #moose", {"tags": ["roads"]})
    store.create_note(S, v, "", "B", "#status/done #moose")
    index.update(S, v)
    tags = {x["tag"]: x["count"] for x in index.all_tags(S, v)}
    assert tags == {"moose": 2, "status": 2, "status/draft": 1, "status/done": 1, "roads": 1}
