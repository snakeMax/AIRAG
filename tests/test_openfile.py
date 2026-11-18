"""Open with AIRAG: Markdown, saved copies, exported pages; re-reading edited saved articles."""
import json
import os
import time

import pytest

from airag import config, history, mylibrary, openfile


REC = {"id": "abc123def456", "query": "hummingbird wings", "title": "How fast do wings beat?", "outcome": "article",
       "article": "# How fast do wings beat?\n\nBetween 10 and 80 times a second [1][2].\n\n## Size\n\nSmall ones beat faster [2].",
       "article_sources": [{"n": 1, "title": "Lab study", "url": "https://example.org/lab", "trust": 8},
                           {"n": 2, "title": "Field notes [draft]", "url": "https://example.com/field"}],
       "created": "2026-11-18T10:00:00+01:00", "model": "demo"}


def test_airag_markdown_round_trip():
    md = mylibrary.article_markdown(REC)
    rec = openfile.parse_markdown(md, "x.md")
    assert rec["from_airag"] and rec["title"] == REC["title"] and rec["query"] == "hummingbird wings"
    assert "## Sources" not in rec["article"] and "Written by AI" not in rec["article"]
    assert "Small ones beat faster [2]." in rec["article"]
    assert [s["n"] for s in rec["article_sources"]] == [1, 2]
    assert rec["article_sources"][0]["url"] == "https://example.org/lab" and rec["article_sources"][0]["trust"] == 8


def test_plain_markdown_and_types():
    rec = openfile.parse_markdown("# My notes\n\nSome text.\n\n## Sources\n\n1. not parsed", "notes.md")
    assert not rec["from_airag"] and rec["title"] == "My notes" and rec["article_sources"] == []
    assert "## Sources" in rec["article"]             # other people's files are kept as they are
    with pytest.raises(openfile.NotOpenable):
        openfile.kind_of("virus.exe")
    with pytest.raises(openfile.NotOpenable):
        openfile.parse_markdown("   ", "empty.md")


def test_saved_json_drops_unsafe_parts():
    raw = json.dumps({**REC, "interactive_html": "<script>steal()</script>", "settings": {"key": "sk-x"},
                      "images": [{"src": "javascript:alert(1)"}, {"src": "data:image/png;base64,AA=="}],
                      "article_sources": [{"n": 1, "url": "javascript:alert(1)", "title": "x"}]})
    rec = openfile.parse_saved_json(raw)
    assert "interactive_html" not in rec and "settings" not in rec
    assert rec["images"] == [{"src": "data:image/png;base64,AA=="}]
    assert "url" not in rec["article_sources"][0]
    assert openfile.parse_saved_json(raw, trusted=True)["interactive_html"]   # own My library files keep it
    with pytest.raises(openfile.NotOpenable):
        openfile.parse_saved_json('{"hello": 1}')


def test_exported_page_round_trip():
    from airag import export_html
    page = export_html.build(REC, "<article><h1>How fast</h1><p>Between 10 and 80 [1]</p></article>", REC["title"],
                             include_explainer=False, pictures=False)
    assert 'type="application/json" id="airag-record"' in page
    rec = openfile.parse_html(page, "export.html")
    assert rec["article"] == REC["article"] and len(rec["article_sources"]) == 2
    # a data copy can't end the script element early
    evil = dict(REC, article="</script><script>alert(1)</script>")
    assert "</script><script>" not in openfile.data_block(evil)


def test_other_web_page_falls_back_to_text():
    page = "<html><head><title>Plain page</title></head><body><article><h1>Plain page</h1>" + \
           "<p>" + "Hummingbirds are small birds that hover. " * 20 + "</p></article></body></html>"
    rec = openfile.parse_html(page, "page.html")
    assert "Hummingbirds are small birds" in rec["article"] and rec["article_sources"] == []


def test_open_file_goes_to_history_without_ai():
    rec = openfile.open_file("notes.md", mylibrary.article_markdown(REC))
    got = history.get(rec["id"])
    assert got["outcome"] == "article" and got["opened_file"] == "notes.md" and len(got["article_sources"]) == 2


def test_edited_saved_markdown_is_read_again(tmp_path):
    s = config.load()
    s["library"]["personal_folder"] = str(tmp_path)
    md_path = mylibrary.save_article(REC, s)
    first = mylibrary.load_saved(s, md_path.stem + ".airag.json")
    assert not first["edited_outside"] and history.get(REC["id"])        # back in History
    text = md_path.read_text(encoding="utf-8").replace("Small ones beat faster [2].", "Small ones beat much faster [2].")
    md_path.write_text(text, encoding="utf-8")
    later = time.time() + 5
    os.utime(md_path, (later, later))
    rec = mylibrary.load_saved(s, md_path.stem + ".airag.json")
    assert rec["edited_outside"] and "much faster" in rec["article"]
    assert rec["article_sources"][0]["trust"] == 8
    assert "much faster" in history.get(REC["id"])["article"]
    assert not mylibrary.load_saved(s, md_path.stem + ".airag.json")["edited_outside"]   # the copy is in sync now


def test_launcher_handover_needs_the_key(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from airag import appctl
    from airag.main import app
    monkeypatch.setattr(appctl, "show", lambda: None)
    f = tmp_path / "notes.md"
    f.write_text("# Notes\n\nHello.", encoding="utf-8")
    secret = tmp_path / "credentials.env"
    secret.write_text("api key", encoding="utf-8")
    c = TestClient(app, base_url="http://127.0.0.1")
    assert c.post("/api/app/open-path", json={"path": str(f)}).status_code == 403
    assert c.post("/api/app/open-path", json={"path": str(f)}, headers={"x-airag-launch": "guess"}).status_code == 403
    ok = c.post("/api/app/open-path", json={"path": str(f)}, headers={"x-airag-launch": appctl.launch_key})
    assert ok.status_code == 200
    c.get("/")
    rid = c.get("/api/app/inbox").json()["id"]
    assert history.get(rid)["title"] == "Notes"
    # only the allowed file types are ever read
    c.post("/api/app/open-path", json={"path": str(secret)}, headers={"x-airag-launch": appctl.launch_key})
    assert "can open" in c.get("/api/app/inbox").json()["error"]
    assert c.get("/api/app/inbox").json() == {}
