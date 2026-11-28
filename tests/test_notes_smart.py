import asyncio

import pytest

from tests import mock

mock.install(settings_patch=False)


@pytest.fixture
def SV(tmp_path):
    from airag.notes import index, store
    s = {"notes": {"root": str(tmp_path / "Notes")}, "llm": {"provider": "anthropic"}}
    v = store.create_vault(s, "Moose", "research")
    store.create_note(s, v, "Notes", "Fences halve collisions",
                      "Intro.\n\n## Results\nFences with wildlife crossings halved moose collisions on the E6.\n\n## Costs\nEach crossing cost NOK 30 million. See [[Verge clearing]].\n", {})
    store.create_note(s, v, "Topics", "Verge clearing", "Cut the grass by the road.\n", {})
    store.create_note(s, v, "Topics", "Moose and roads", "See [[Fences halve collisions]]. Verges matter too.\n", {})
    store.create_note(s, v, "Topics", "Fence-end hotspots", "Crashes move to where the barrier stops.\n", {})
    store.create_note(s, v, "Topics", "Cooking", "Nothing about animals.\n", {})
    index.update(s, v)
    return s, v


def test_retrieve_tiers_and_link_neighbours(SV):
    from airag.notes import smart
    s, v = SV
    found = smart.retrieve(s, v, {"terms": ["fences", "collisions"], "alt": ["barrier"]})
    tiers = smart._tiers(found)
    assert tiers["direct"][0]["title"] == "Fences halve collisions"
    rel = [x["title"] for x in tiers["related"]]
    assert "Fence-end hotspots" in rel and "Verge clearing" in rel       # other word + link neighbour
    assert "Moose and roads" in [x["title"] for x in tiers["direct"] + tiers["related"]]
    assert "Cooking" not in [x["title"] for t in tiers.values() for x in t]


def test_ask_cites_only_sent_sections_and_fences_them(SV, monkeypatch):
    from airag.notes import smart
    s, v = SV
    smart._PLAN_CACHE.clear()
    calls = []

    async def fake(llm, system, user, max_tokens=0):
        calls.append((system, user))
        if "plan a search" in system:
            return {"intent": "Do fences work", "terms": ["fences", "collisions"], "alt": ["barrier", "crash; DROP TABLE"]}
        return {"answer": "They halved collisions [1], and moved crashes to the fence ends [2]. Also [9].", "missing": "Costs over time."}
    monkeypatch.setattr(smart, "complete_json", fake)
    monkeypatch.setattr(smart, "get_llm", lambda settings, task=None: None)
    r = asyncio.run(smart.ask(s, v, "Do fences stop moose collisions?"))
    assert "[9]" not in r["answer"] and "[1]" in r["answer"]
    assert [c["n"] for c in r["cites"]] == [1, 2]
    assert r["cites"][0]["title"] == "Fences halve collisions"
    assert 1 <= r["read"] <= smart.MAX_SECTIONS
    assert "drop table" in r["plan"]["alt"][1] and ";" not in r["plan"]["alt"][1]   # cleaned to plain words
    # plan is cached: asking again makes only the answer call
    n = len(calls)
    asyncio.run(smart.ask(s, v, "Do fences stop moose collisions?"))
    assert len(calls) == n + 1


def test_ask_empty_when_nothing_matches(SV, monkeypatch):
    from airag.notes import smart
    s, v = SV
    smart._PLAN_CACHE.clear()

    async def fake(llm, system, user, max_tokens=0):
        return {"terms": ["zebra"], "alt": []}
    monkeypatch.setattr(smart, "complete_json", fake)
    monkeypatch.setattr(smart, "get_llm", lambda settings, task=None: None)
    r = asyncio.run(smart.ask(s, v, "zebra"))
    assert r["answer"] == "" and r["read"] == 0


def test_ask_routes_web_questions_and_articles(SV, monkeypatch):
    from airag.notes import smart
    s, v = SV
    smart._PLAN_CACHE.clear()
    seen = []

    async def fake(llm, system, user, max_tokens=0):
        seen.append(system)
        if "plan a search" in system:
            if "latest" in user:
                return {"route": "research", "query": "moose fence studies 2026", "terms": ["fences"]}
            if "write" in user:
                return {"route": "article", "terms": ["fences", "collisions"], "alt": []}
            return {"route": "bogus", "terms": ["fences"]}
        return {"answer": "# Fences\n\n## A\nThey work [1].", "missing": ""}
    monkeypatch.setattr(smart, "complete_json", fake)
    monkeypatch.setattr(smart, "get_llm", lambda settings, task=None: None)
    r = asyncio.run(smart.ask(s, v, "research the latest fence studies"))
    assert r["route"] == "research" and r["query"] == "moose fence studies 2026" and len(seen) == 1   # no notes read
    r = asyncio.run(smart.ask(s, v, "write an article on fences and collisions"))
    assert r["route"] == "article" and "Write a short article" in seen[-1] and r["cites"][0]["n"] == 1
    r = asyncio.run(smart.ask(s, v, "fences?"))
    assert r["route"] == "notes"                                           # unknown route -> notes
    r = asyncio.run(smart.ask(s, v, "research the latest fence studies", force="notes"))
    assert r["route"] == "notes"                                           # Ask my notes instead
