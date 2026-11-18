"""Offline mode: no web access anywhere, sources from your own files and History, optional local writer."""
import asyncio

from airag import config, fetch, history, offline


def _set(**lib):
    config.save({"library": lib})


def test_web_paths_are_closed(monkeypatch):
    _set(offline=True)
    try:
        real = getattr(fetch, "real_fetch_page", fetch.fetch_page)     # the tests' mock replaces it
        page = asyncio.run(real("https://example.org/offline-check", config.load()["fetch"]))
        assert not page.ok and "Offline" in page.error
        from airag.search import get_search, get_image_search
        s = config.load()
        assert asyncio.run(get_search(s).text("anything")) == []
        assert get_image_search(s) is not None and asyncio.run(get_image_search(s).images("x")) == []
        from airag import wikis
        assert asyncio.run(wikis.search({"api": "https://en.wikipedia.org/w/api.php"}, "x")) == []
    finally:
        _set(offline=False)


def test_local_writer_only_when_set_up(monkeypatch):
    s = config.load()
    s["library"].update({"offline": True, "offline_writer": "local", "offline_provider": "openai_compatible",
                         "offline_model": "qwen"})
    assert offline.writer_override(s) is None                  # no local server configured
    s["llm"]["providers"]["openai_compatible"] = {"base_url": "http://127.0.0.1:8080/v1", "model": "x"}
    assert offline.writer_override(s) == {"provider": "openai_compatible", "model": "qwen"}
    from airag.llm import get_llm
    assert "OpenAI-compatible" in get_llm(s).describe() and "qwen" in get_llm(s).describe()
    s["llm"]["providers"]["openai_compatible"]["base_url"] = "https://api.example.com/v1"   # not local
    assert offline.writer_override(s) is None
    s["library"]["offline_writer"] = "current"
    assert offline.writer_override(s) is None


def test_history_is_a_source():
    history.save({"id": "off-h1", "query": "hummingbird wing beats", "title": "Hummingbird wings", "outcome": "article",
                  "article": "# Hummingbird wings\n\nHummingbird wings beat 50 times a second."}, 50)
    hits = offline.history_matches(["hummingbird", "wings", "beat"])
    assert hits and hits[0]["id"] == "off-h1"
    assert offline.history_matches(["hummingbird", "wings"], skip_id="off-h1") == []


def test_offline_search_reads_no_web(monkeypatch):
    from tests import mock
    mock.install()
    from airag import pipeline
    calls = []
    real = fetch.fetch_page

    async def spy(url, cfg):
        calls.append(url)
        return await real(url, cfg)
    monkeypatch.setattr(pipeline, "fetch_page", spy)
    history.save({"id": "off-h2", "query": "hummingbird wing beats", "title": "Hummingbird wing beats",
                  "outcome": "article", "article": "# Hummingbird wing beats\n\nHummingbird wing beats are fast: "
                  "most hummingbird species beat their wings 50 times a second." * 3}, 50)
    _set(offline=True, offline_writer="current")
    try:
        r = pipeline.Research("hummingbird wing beats", "auto", config.load(), _noop)
        assert r.use_web is False
        rec = asyncio.run(r.run())
        assert not [u for u in calls if u.startswith("http")]
        assert any(s.get("domain") == "history" for s in rec.get("sources") or [])
        assert "Offline" in (rec.get("search") or "")
    finally:
        _set(offline=False)


async def _noop(ev):
    return None


def test_api_turn_on_and_off():
    from fastapi.testclient import TestClient
    from airag.main import app
    c = TestClient(app, base_url="http://127.0.0.1")
    c.get("/")
    st = c.get("/api/offline").json()
    assert st["on"] is False and "current" in st
    assert c.post("/api/offline", json={"on": True, "writer": "local", "provider": "nope"}).status_code == 400
    st = c.post("/api/offline", json={"on": True, "writer": "current"}).json()
    assert st["on"] and offline.on()
    assert c.post("/api/offline", json={"on": False}).json()["on"] is False
