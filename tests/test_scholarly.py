"""Blocked pages and Europe PMC rescue (network replaced by fakes)."""
import asyncio

import httpx

from airag import fetch, scholarly

XML = ('<?xml version="1.0"?><article><front><journal-meta><journal-title>Case Reports</journal-title></journal-meta>'
       '<article-meta><contrib><surname>Sinha</surname></contrib></article-meta></front>'
       '<abstract><p>Stimulants raise heart rate.</p></abstract>'
       '<body><sec><title>1. Introduction</title><p>Adult ADHD affects 3% to 5% [<xref rid="B1">1</xref>].</p></sec>'
       '<ref-list><ref>Some reference</ref></ref-list></body></article>')


def test_bot_check_pages_are_recognised():
    assert fetch.looks_blocked("Checking your browser before accessing pmc.ncbi.nlm.nih.gov", "Checking your browser - reCAPTCHA")
    assert fetch.looks_blocked("Just a moment...", "")
    assert not fetch.looks_blocked("Amphetamine is dosed at 5 mg once or twice daily. " * 200, "Label")


def test_ids_and_titles():
    assert scholarly._ids("https://pmc.ncbi.nlm.nih.gov/articles/PMC4992783/")[0] == "PMC4992783"
    assert scholarly._ids("https://pubmed.ncbi.nlm.nih.gov/27579185/")[1] == "27579185"
    assert scholarly._ids("https://doi.org/10.1155/2016/2343691")[2] == "10.1155/2016/2343691"
    assert scholarly._clean_title("(PDF) Effect of amphetamines on blood pressure - ResearchGate") == "Effect of amphetamines on blood pressure"
    assert scholarly._clean_title("Acute Cardiovascular Responses to Amphetamine ...") == "Acute Cardiovascular Responses to Amphetamine"
    assert scholarly.is_scholarly("https://www.sciencedirect.com/science/article/pii/S2215036625000628")
    assert not scholarly.is_scholarly("https://www.example.com/blog/post")


def test_full_text_keeps_abstract_and_body_only():
    t = scholarly._xml_text(XML)
    assert "Stimulants raise heart rate." in t and "## 1. Introduction" in t and "3% to 5%" in t
    assert "Sinha" not in t and "Some reference" not in t and "[1]" not in t


def test_rescue_reads_open_access_full_text(monkeypatch):
    def handler(req: httpx.Request):
        if req.url.path.endswith("/search"):
            return httpx.Response(200, json={"resultList": {"result": [{"title": "Adult ADHD Medications", "pmcid": "PMC4992783",
                                                                       "isOpenAccess": "Y", "abstractText": "x" * 100}]}})
        return httpx.Response(200, text=XML)
    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    p = asyncio.run(scholarly.rescue("https://pmc.ncbi.nlm.nih.gov/articles/PMC4992783/", "Checking your browser"))
    assert p.ok and p.via == "europepmc" and "Full text from Europe PMC" in p.text and "3% to 5%" in p.text


def test_rescue_falls_back_to_abstract_by_title(monkeypatch):
    seen = []

    def handler(req: httpx.Request):
        seen.append(req.url.params.get("query"))
        return httpx.Response(200, json={"resultList": {"result": [{"title": "Effect of amphetamines on blood pressure.",
                                                                   "isOpenAccess": "N", "abstractText": "<h4>Background</h4>Amphetamines raise systolic blood pressure by a few mmHg in randomised trials of adults with ADHD."}]}})
    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    p = asyncio.run(scholarly.rescue("https://www.researchgate.net/publication/290026921_Effect_of_amphetamines_on_blood_pressure",
                                     "(PDF) Effect of amphetamines on blood pressure - ResearchGate"))
    assert p.ok and p.via == "abstract" and "Only the abstract" in p.text and "mmHg" in p.text
    assert seen == ['TITLE:"Effect of amphetamines on blood pressure"']


def test_search_survives_blocked_pages(monkeypatch):
    """Bot checks and 403s are never judged as pages; replacements are read; snippets are judged once."""
    from tests import mock
    mock.install()
    from airag import config, pipeline
    calls = {"fetch": [], "assess": 0}

    async def fetch_some_blocked(url, cfg, title=""):
        calls["fetch"].append(url)
        if "nature.com" in url or "reddit.com" in url:
            return fetch.Page(url, error="The site showed a bot check instead of the page", blocked=True)
        return await mock.fake_fetch(url, cfg, title)
    monkeypatch.setattr(pipeline, "fetch_page", fetch_some_blocked)
    real_assess = pipeline.prompts.assess

    def counting(*a, **k):
        calls["assess"] += 1
        return real_assess(*a, **k)
    monkeypatch.setattr(pipeline.prompts, "assess", counting)

    async def noop(ev):
        return None
    r = pipeline.Research("hummingbird wing beats", "article", config.load(), noop)
    rec = asyncio.run(r.run())
    srcs = rec["sources"]
    blocked = [s for s in srcs if s.get("blocked")]
    assert blocked, "some pages were blocked"
    assert calls["assess"] == sum(1 for s in srcs if s.get("status") == "assessed" and s.get("via") not in ("snippet",))
    assert any(s.get("via") == "snippet" for s in srcs)          # a blocked page's snippet was used
    readable = [s for s in srcs if s.get("status") == "assessed" and s.get("via") != "snippet"]
    assert len(readable) >= min(len([s for s in srcs if not s.get("blocked")]), 6)    # replacements filled the round
