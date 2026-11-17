import asyncio

import pytest

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
