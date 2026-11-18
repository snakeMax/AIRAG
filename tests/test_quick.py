import asyncio

from tests import mock
from tests.test_pipeline import settings

mock.install(settings_patch=False)


def quick(query, s=None, **kw):
    from airag.quick import QuickResearch
    events = []

    async def emit(e):
        events.append(e)
    rec = asyncio.run(QuickResearch(query, s or settings(), emit, "en", **kw).run())
    return rec, events


def test_quick_answer_is_light():
    rec, events = quick("hummingbird wing beats")
    assert rec["outcome"] == "article" and rec["quick"] is True
    assert rec["article"].startswith("# ")
    assert 1 <= len(rec["article_sources"]) <= 3
    steps = [e for e in events if e["type"] == "step"]
    assert sum(1 for e in steps if e["id"].startswith("search")) and not any(e["id"].startswith("search2") for e in steps)
    read = [s for s in rec["sources"] if s.get("status") not in ("found", None)]
    assert len(read) <= 3 + 2 * 3          # at most 3 readable pages (plus replacements for unreadable ones)
    assert rec["plan"]["quick"] and rec["plan"]["direct_queries"] == ["hummingbird wing beats"]


def test_live_settings_never_grow_a_quick_search():
    from airag.quick import QuickResearch, PROFILE

    async def emit(e):
        pass
    q = QuickResearch("hummingbird wing beats", settings(), emit, "en")
    q.r["max_rounds"] = 9
    q.apply_profile()
    assert q.r["max_rounds"] == PROFILE["max_rounds"] == 2 and q.r["sources_per_round"] == 3


def test_quick_search_updates_the_article():
    from airag import history, versions
    from tests.test_pipeline import run
    art, _ = run("hummingbird wing beats", mode="article")
    before = art["article"]
    rec, events = quick("does decaf count", context_id=art["id"], update=True)
    saved = history.get(art["id"])
    assert saved["article"].startswith(before.rstrip())
    assert "## Does decaf count?" in saved["article"]
    assert len(saved["article_sources"]) > len(art["article_sources"])
    ns = [s["n"] for s in saved["article_sources"]]
    assert len(ns) == len(set(ns))               # new sources are numbered after the old ones
    v = versions.listing(art["id"])
    assert v["items"][0]["kind"] == "quick"      # newest first
    assert any(e["type"] == "done" and e.get("quick") for e in events)


def test_quick_search_without_updating_makes_a_separate_answer():
    from airag import history
    from tests.test_pipeline import run
    art, _ = run("hummingbird wing beats", mode="article")
    rec, _ = quick("does decaf count", context_id=art["id"], update=False)
    assert rec["id"] != art["id"] and rec["quick_of"] == art["id"]
    assert history.get(art["id"])["article"] == art["article"]
    assert rec["plan"]["direct_queries"][0] != "does decaf count"    # the article's subject is searched too


def test_quick_endpoint_streams_an_answer():
    from fastapi.testclient import TestClient
    mock.install()
    from airag.main import app
    with TestClient(app, base_url="http://127.0.0.1") as c:
        c.get("/")
        r = c.post("/api/quick", json={"query": "hummingbird wing beats", "ui_lang": "en"})
        assert r.status_code == 200
        assert '"done"' in r.text
        assert c.post("/api/quick", json={"query": "x", "context_id": "missing-id"}).status_code == 400


def test_nothing_usable_tries_three_simpler_searches():
    rec, events = quick("none quick test")
    steps = {e["id"]: e for e in events if e["type"] == "step"}
    assert "retry" in steps and "search2" in steps
    assert len(rec["tried"]) == 1 + 3


def test_good_results_need_no_extra_searches():
    rec, events = quick("hummingbird wing beats")
    assert not any(e["type"] == "step" and e["id"] == "retry" for e in events)
    assert len(rec["tried"]) == 1
