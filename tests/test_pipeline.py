import asyncio

from airag import config
from tests import mock

mock.install(settings_patch=False)


def settings():
    s = config.load()
    s["llm"]["provider"] = "mock"
    s["llm"]["providers"]["mock"] = {"model": "demo"}
    s["search"]["backend"] = "mocksearch"
    s["search"]["image_backend"] = "none"
    return s


def run(query, mode="auto", s=None, library=False):
    from airag.pipeline import Research
    events = []

    async def emit(e):
        events.append(e)
    rec = asyncio.run(Research(query, mode, s or settings(), emit, library, "en").run())
    return rec, events


def test_article():
    rec, events = run("hummingbird wing beats")
    assert rec["outcome"] == "article"
    assert rec["article"].startswith("# ")
    assert rec["article_sources"] and all("n" in s for s in rec["article_sources"])
    assert rec["interactive"]["suitable"] is True
    assert any(e["type"] == "token" for e in events)


def test_results_when_a_page_answers_directly():
    rec, _ = run("results test")
    assert rec["outcome"] == "results"
    assert rec["results"]["best"]


def test_suggestions_when_nothing_found():
    rec, _ = run("none test")
    assert rec["outcome"] == "suggestions"
    assert rec["suggestions"]["items"]


def test_history_saved_and_pruned():
    from airag import history
    s = settings()
    s["app"]["history_limit"] = 2
    for q in ("results one", "results two", "results three"):
        run(q, s=s)
    assert len(history.listing()) <= 2


def test_library_only(tmp_path):
    (tmp_path / "birds.md").write_text("# Birds\n\nHummingbird wings beat 53 times per second.\n", encoding="utf-8")
    s = settings()
    s["library"]["folders"] = [str(tmp_path)]
    s["library"]["web_too"] = False
    rec, _ = run("hummingbird wing beats", s=s, library=True)
    assert rec["web"] is False
    assert any(src.get("local") for src in rec["sources"])


def test_article_from_previous_results_reuses_sources():
    from airag.pipeline import Research
    rec, _ = run("results test")
    assert rec["outcome"] == "results"
    events = []

    async def emit(e):
        events.append(e)
    art = asyncio.run(Research("ignored", "article", settings(), emit, False, "en", from_id=rec["id"]).run())
    steps = [e["id"] for e in events if e["type"] == "step"]
    assert not any(s.startswith("search") for s in steps), steps      # no new web searches
    assert "reuse" in steps
    assert art["outcome"] == "article" and art["query"] == rec["query"]
    assert {s["url"] for s in art["article_sources"]} <= {s["url"] for s in rec["sources"]}


def test_date_range_limits_searches():
    from airag.pipeline import Research
    from airag.search.base import date_range, range_to_period
    assert date_range("2026-02-01..2026-01-01") == ("2026-01-01", "2026-02-01")
    assert date_range("..2026-01-01")[0] == "1990-01-01"
    assert date_range("week") is None and range_to_period("week") == "week"
    seen = []
    from tests import mock as m
    orig = m.MockSearch.text

    async def spy(self, q, n=10, recent=""):
        seen.append(recent)
        return await orig(self, q, n)
    m.MockSearch.text = spy
    try:
        events = []

        async def emit(e):
            events.append(e)
        rec = asyncio.run(Research("hummingbird wing beats", "auto", settings(), emit, False, "en",
                                   date_from="2026-01-01", date_to="2026-03-01").run())
    finally:
        m.MockSearch.text = orig
    assert seen and all(r == "2026-01-01..2026-03-01" for r in seen)
    assert rec["dates"] == ["2026-01-01", "2026-03-01"]


def test_pages_outside_the_date_range_are_left_out():
    from airag.pipeline import Research

    async def emit(e):
        pass
    r = Research("x", "auto", settings(), emit, date_from="2026-11-01", date_to="2026-11-30")
    old, new, undated = {"published": "2024-05-02"}, {"published": "Nov 12, 2026"}, {"date": ""}
    for s in (old, new, undated):
        r.check_dates(s)
    assert old.get("out_of_range") and not new.get("out_of_range") and not undated.get("out_of_range")


def test_pages_that_cant_help_skip_the_ai():
    from airag.pipeline import Research

    async def emit(e):
        pass
    r = Research("x", "auto", settings(), emit)
    r.plan = {"key_terms": ["hummingbird", "wingbeat", "kolibri", "vingeslag"]}
    r.terms = ["hummingbird", "wingbeat", "kolibri", "vingeslag"]
    text = "A page about hummingbird flight. " * 40
    a = {"url": "https://a.example/1", "prior": 5, "prior_label": "x"}
    b = {"url": "https://mirror.example/1", "prior": 5, "prior_label": "x"}
    c = {"url": "https://c.example/2", "prior": 5, "prior_label": "x"}
    assert asyncio.run(r.skip_without_ai(a, text)) is False
    assert asyncio.run(r.skip_without_ai(b, text)) is True and b["relevance"] == 0       # same text again
    assert asyncio.run(r.skip_without_ai(c, "Cooking pasta at home. " * 40)) is True    # off topic
