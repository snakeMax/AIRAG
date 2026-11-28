import asyncio

import httpx
import pytest

from tests import mock

mock.install(settings_patch=False)


def test_wikimedia_article_addresses():
    from airag import wikipage
    assert wikipage.article("https://en.wikipedia.org/wiki/Moose") == ("https://en.wikipedia.org/w/api.php", "Moose")
    assert wikipage.article("https://no.m.wikipedia.org/wiki/Elg_(dyr)") == ("https://no.wikipedia.org/w/api.php", "Elg (dyr)")
    assert wikipage.article("https://en.wikipedia.org/w/index.php?title=Moose") [1] == "Moose"
    for not_article in ["https://en.wikipedia.org/wiki/Special:Random", "https://en.wikipedia.org/wiki/File:Moose.jpg",
                        "https://en.wikipedia.org/w/index.php?title=Moose&action=edit", "https://example.org/wiki/Moose",
                        "https://upload.wikimedia.org/x.jpg", "https://en.wikipedia.org/wiki/Talk:Moose"]:
        assert wikipage.article(not_article) is None, not_article


def test_wikipedia_read_uses_api_with_honest_agent(monkeypatch):
    from airag import wikipage
    seen = {}

    def handler(request):
        seen["ua"] = request.headers["user-agent"]
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json={"query": {"pages": [{"title": "Moose", "fullurl": "https://en.wikipedia.org/wiki/Moose",
            "description": "Large deer", "extract": "The moose is a deer.\n\n== Behaviour ==\nThey swim.\n\n=== Diet ===\nPlants.\n\n== References ==\nX"}]}})
    real = httpx.AsyncClient
    monkeypatch.setattr(wikipage.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    p = asyncio.run(wikipage.read("https://en.wikipedia.org/wiki/Moose"))
    assert p.ok and p.via == "wikipedia-api" and "## Behaviour" in p.text and "### Diet" in p.text
    assert "github.com/snakeMax/AIRAG" in seen["ua"] and "Mozilla" not in seen["ua"]
    assert seen["params"]["titles"] == "Moose" and seen["params"]["explaintext"] == "1"


def test_wikipedia_429_retries_once_and_does_not_block_site(monkeypatch):
    from airag import fetch, wikipage
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(429, headers={"retry-after": "0"})
    real = httpx.AsyncClient
    monkeypatch.setattr(wikipage.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    p = asyncio.run(wikipage.read("https://en.wikipedia.org/wiki/Moose"))
    assert not p.ok and len(calls) == 2 and not p.blocked


def test_sections_skip_references_and_pick_matching():
    from airag.passages import select_sections, tokenize
    text = ("Moose are large deer.\n\n## Taxonomy\n" + "Cervidae genus Alces lineage. " * 80 +
            "\n\n## Road collisions\nMoose collisions with cars fell by half after fences were built in 2019. " + "More on fences. " * 30 +
            "\n\n## Diet\n" + "Leaves and twigs. " * 80 + "\n\n## References\n" + "Smith 2019 fences collisions moose. " * 200)
    terms = set(tokenize("moose road collisions fences"))
    ex, info = select_sections(text, terms, 1200)
    assert "## Road collisions" in ex and "Smith 2019" not in ex and ex.startswith("Moose are large deer.")
    assert info["skipped"] == 1 and info["sections"] == 4 and info["read"] < info["sections"]
    ex2, _ = select_sections(text, set(), 1200, pick=["Diet"])
    assert "## Diet" in ex2


def test_long_page_ai_pick_only_when_words_dont_match(monkeypatch):
    import asyncio as aio
    from airag import pipeline
    secs = "".join(f"\n\n## Part {i}\n" + "Unrelated words here. " * 200 for i in range(12))
    text = "Intro." + secs + "\n\n## Antlers\nShed every winter. " + "Bone. " * 50
    r = object.__new__(pipeline.Research)
    r.terms, r.tried, r.r, r.query, r.plan, r.s = ["antler"], [], {"passage_chars": 3500, "long_page_pick": True}, "when do moose lose their horns", {"intent": "x"}, {}
    r._sem_llm = aio.Semaphore(1)
    calls = []

    async def fake(llm, system, user, max_tokens=0):
        calls.append(user)
        return {"sections": ["Antlers", "Not a heading"]}
    monkeypatch.setattr(pipeline, "complete_json", fake)
    monkeypatch.setattr(pipeline, "get_llm", lambda s, task=None: None)
    s = {"title": "Moose", "url": "u"}
    r.terms = ["horn"]                                        # the words don't match any section
    ex = aio.run(r.page_excerpt(s, text))
    assert len(calls) == 1 and "## Antlers" in ex and s["read_info"]["ai_pick"] == 1
    s2 = {"title": "Moose", "url": "u"}
    r.terms = ["antler", "shed", "winter"]                    # they do: no AI call
    aio.run(r.page_excerpt(s2, text))
    assert len(calls) == 1 and "ai_pick" not in s2["read_info"]
