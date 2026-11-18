"""Version history: rewrites, added answers and regenerations become versions; Undo/Restore never delete."""
from airag import config, history, rewrite, versions


def _rec(rid):
    history.save({"id": rid, "query": "q", "outcome": "article", "article": "# H\n\nFirst text [1].",
                  "article_sources": [{"n": 1, "url": "https://a.org"}]})


def test_rewrites_become_versions_and_undo_restore_keep_everything():
    _rec("ver1")
    s = config.load()
    rewrite.apply(s, "ver1", "First text [1].", "Second text [1].", "clearer")
    rewrite.apply(s, "ver1", "Second text [1].", "Third text [1].", "shorter")
    v = versions.listing("ver1")
    assert [x["n"] for x in v["items"]] == [3, 2, 1] and v["pos"] == 3
    assert v["items"][0]["note"] == "shorter" and v["items"][2]["kind"] == "first"
    versions.undo("ver1")
    assert "Second text" in history.get("ver1")["article"] and versions.listing("ver1")["pos"] == 2
    versions.undo("ver1")
    assert "First text" in history.get("ver1")["article"]
    assert versions.undo("ver1") is None                      # nothing before the first version
    versions.restore("ver1", 3)
    assert "Third text" in history.get("ver1")["article"]
    assert len(versions.listing("ver1")["items"]) == 3        # nothing was deleted


def test_versions_go_when_the_article_leaves_history():
    _rec("ver2")
    rewrite.apply(config.load(), "ver2", "First text [1].", "Other text [1].")
    assert versions.listing("ver2")["items"]
    history.delete("ver2")
    assert versions.listing("ver2")["items"] == []


def test_only_the_last_versions_are_kept():
    _rec("ver3")
    s = config.load()
    cur = "First text [1]."
    for i in range(versions.MAX + 5):
        new = f"Text number {i} [1]."
        rewrite.apply(s, "ver3", cur, new)
        cur = new
    items = versions.listing("ver3")["items"]
    assert len(items) == versions.MAX and items[0]["n"] == versions.MAX + 6


def test_regenerate_job_keeps_added_answers_and_can_be_undone():
    import json
    from fastapi.testclient import TestClient
    from tests import mock
    mock.install()
    from airag.main import app
    art = mock.ARTICLE.rstrip() + "\n\n## Why are small ones faster?\n\nSmaller wings move less air [1].\n"
    history.save({"id": "regen1", "query": "hummingbird wings", "outcome": "article", "article": art,
                  "article_sources": [{"n": 1, "url": "https://a.org", "title": "A", "domain": "a.org", "summary": "s"},
                                      {"n": 2, "url": "https://b.org", "title": "B", "domain": "b.org", "summary": "s"}],
                  "thread": [{"q": "Why are small ones faster?", "mode": "ask", "a": "Smaller wings move less air [1].",
                              "added": True}]})
    with TestClient(app, base_url="http://127.0.0.1") as c:
        c.get("/")
        r = c.post("/api/regenerate", json={"id": "regen1", "instructions": "simpler"})
        events = [json.loads(x) for x in r.text.splitlines() if x.strip()]
        assert events[-1]["type"] == "done", events[-3:]
        rec = history.get("regen1")
        assert rec["article"].startswith("# ") and "Put simply" in rec["article"]
        assert "## Why are small ones faster?" in rec["article"]          # the reader's added answer is kept
        v = c.get("/api/versions/regen1").json()
        assert v["items"][0]["kind"] == "regenerated" and v["items"][0]["note"] == "simpler"
        c.post("/api/versions/regen1/undo")
        assert "Put simply" not in history.get("regen1")["article"]
