"""Tags: Markdown properties, saving, editing a saved copy, library search order, Suggest tags."""
import asyncio

from airag import config, history, mylibrary, openfile, tags
from airag.library import Library

REC = {"id": "tag111aaa222", "query": "electric cars norway", "title": "EV sales", "outcome": "article",
       "article": "# EV sales\n\nMost new cars sold are electric [1].", "created": "2026-11-18T10:00:00+01:00",
       "article_sources": [{"n": 1, "title": "OFV", "url": "https://ofv.no"}], "model": "demo",
       "translations": {"nb": "# Elbilsalg\n\nDe fleste nye biler er elektriske [1].", "de": "# E-Autos"}}


def test_clean_and_front_matter():
    assert tags.clean(["#EV", "ev", " Sales 2026 ", "cars/ev", ""]) == ["ev", "sales 2026", "cars/ev"]
    assert tags.yaml_list(["ev", "sales 2026"]) == '[airag, ev, "sales 2026"]'
    assert tags.from_front_matter("---\ntags:\n  - One\n  - two\n---\n") == ["one", "two"]
    assert tags.matches(["electric cars"], "How many electric cars in Norway?")
    assert not tags.matches(["car"], "carpets")


def test_save_with_tags_and_chosen_translations(tmp_path):
    s = config.load()
    s["library"]["personal_folder"] = str(tmp_path)
    rec = {**REC, "tags": ["ev", "Norway"]}
    md = mylibrary.save_article(rec, s, translations=["nb"])
    assert "tags: [airag, ev, norway]" in md.read_text(encoding="utf-8")
    saved = mylibrary.load_saved(s, md.stem + ".airag.json")
    assert saved["tags"] == ["ev", "norway"] and list(saved["translations"]) == ["nb"]
    # opened elsewhere: tags and translations come along, the default tag stays out
    back = openfile.parse_saved_json((md.with_name(md.stem + ".airag.json")).read_text(encoding="utf-8"))
    assert back["tags"] == ["ev", "norway"] and "nb" in back["translations"]
    # changing tags rewrites the properties in place, without marking the file as edited outside AIRAG
    history.save({**rec, "saved_path": str(md)}, 50)
    mylibrary.set_tags({**rec, "saved_path": str(md), "tags": ["sales data"]}, s)
    text = md.read_text(encoding="utf-8")
    assert 'tags: [airag, "sales data"]' in text and text.count("tags:") == 1
    assert not mylibrary.load_saved(s, md.stem + ".airag.json")["edited_outside"]


def test_tagged_files_are_read_first(tmp_path):
    folder = tmp_path / "notes"
    folder.mkdir()
    (folder / "a.md").write_text("# A\n\nElectric cars are popular. Electric cars everywhere. Electric cars.", encoding="utf-8")
    (folder / "b.md").write_text("---\ntags: [electric cars]\n---\n# B\n\nNotes about batteries.", encoding="utf-8")
    lib = Library(tmp_path / "lib.db")
    lib.sync([str(folder)], [".md"])
    hits = lib.search(["electric cars"], limit=5)
    assert hits[0]["title"] == "B" and hits[0]["tagged"] and hits[0]["tags"] == ["electric cars"]
    assert hits[1]["title"] == "A"


def test_suggest_tags_is_a_job():
    from fastapi.testclient import TestClient
    from tests import mock
    mock.install()
    from airag.main import app
    history.save(dict(REC), 50)
    c = TestClient(app, base_url="http://127.0.0.1")
    c.get("/")
    r = c.post(f"/api/tags/{REC['id']}/suggest")
    assert r.status_code == 200, r.text
    assert r.json()["tags"] == ["hummingbirds", "wing speed", "birds"]      # "airag" is left out
    r = c.post(f"/api/tags/{REC['id']}", json={"tags": ["EV", "ev", "airag"]})
    assert r.json()["tags"] == ["ev"] and history.get(REC["id"])["tags"] == ["ev"]
