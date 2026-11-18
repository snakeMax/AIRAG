"""Agent tools, follow-ups, the calculator, rewrite."""
import asyncio

import pytest

from airag import config, history, tools
from airag.tools.calc import calculate, check


def test_calculator_is_exact_and_safe():
    assert asyncio.run(calculate("x^2 - 5x + 6 = 0"))[1] == "[2, 3]"
    assert asyncio.run(calculate("integrate(exp(-x**2),(x,-oo,oo))"))[1] == "sqrt(pi)"
    assert asyncio.run(calculate("15% * 240"))[1] == "36"
    for bad in ["__import__('os')", "().__class__", "eval(1)", "os.system('x')", "9**999999", "lambda: 1", "x.real"]:
        with pytest.raises(ValueError):
            check(bad)


def test_tool_sets_and_refusals():
    s = config.defaults()
    assert "calculator" in tools.enabled(s, "standard") and "pin_article" not in tools.enabled(s, "standard")
    s["agent_tools"] = {"sets": {"standard": ["datetime"]}}
    sess = tools.Session("standard", tools.enabled(s, "standard"), {"settings": s})
    first = asyncio.run(sess.call({"name": "calculator", "args": {"expression": "1+1"}}))
    assert "not available" in first and "calculator" in sess.refused
    assert "Don't ask for it again" in asyncio.run(sess.call({"name": "calculator", "args": {}}))
    assert tools.parse_call('TOOL {"name": "datetime", "args": {}} and then...')["name"] == "datetime"
    assert tools.parse_call("Just an answer") is None


def test_rewrite_finds_the_paragraph():
    from airag.rewrite import locate
    md = "# Title\n\nFirst paragraph about bees [1].\n\nSecond one: hummingbirds beat wings 50 times a second [2].\n"
    s, e = locate(md, "hummingbirds beat wings 50 times a second")
    assert md[s:e].startswith("Second one") and md[s:e].endswith("[2].")
    assert locate(md, "volcanoes erupt") is None


def test_rewrite_apply_is_kept_in_the_answers():
    from airag import config, rewrite
    history.save({"id": "rw1", "query": "q", "outcome": "article", "article": "# H\n\nOld text [1].\n"}, 50)
    rewrite.apply(config.load(), "rw1", "Old text [1].", "New text [1].", "simpler")
    rec = history.get("rw1")
    assert "New text [1]." in rec["article"] and "Old text" not in rec["article"]
    last = rec["thread"][-1]
    assert last["mode"] == "rewrite" and last["q"] == "simpler" and last["a"] == "New text [1]." and last["added"]


def test_followup_uses_the_calculator(monkeypatch):
    from tests import mock
    mock.install()
    from airag import followup
    history.save({"id": "fu1", "query": "hummingbird wing beats", "outcome": "article", "article": "# H\n\nText [1].",
                  "article_sources": [{"n": 1, "url": "https://a.org", "title": "A", "domain": "a.org"}],
                  "sources": []}, 100)
    s = config.load()

    async def go():
        return [ev async for ev in followup.answer(s, "fu1", "How many times faster is the fastest?", "ask")]
    evs = asyncio.run(go())
    assert any(e["type"] == "tool" and e["name"] == "calculator" for e in evs)
    assert any("80 / 10 = 8" in e.get("text", "") for e in evs if e["type"] == "tool_result")
    assert evs[-1]["type"] == "done" and "factor of 8" in evs[-1]["entry"]["a"]
    assert history.get("fu1")["thread"][-1]["tools"] == ["Calculator"]


def test_ai_tools_run_as_background_jobs():
    """Follow-ups (and every other AI tool) are queued jobs that show in the activity list; the page still gets
    the answer streamed, and the job finishes even if nobody is listening."""
    import json
    from fastapi.testclient import TestClient
    from tests import mock
    mock.install()
    from airag import runs
    from airag.main import app
    history.save({"id": "fu2", "query": "hummingbird wing beats", "outcome": "article", "article": "# H\n\nText [1].",
                  "article_sources": [{"n": 1, "url": "https://a.org", "title": "A", "domain": "a.org"}],
                  "sources": []}, 100)
    with TestClient(app, base_url="http://127.0.0.1") as c:
        c.get("/")
        r = c.post("/api/followup", json={"id": "fu2", "question": "How many times faster is the fastest?", "mode": "ask"})
        events = [json.loads(line) for line in r.text.splitlines() if line.strip()]
        assert events[-1]["type"] == "done" and "factor of 8" in events[-1]["entry"]["a"]
        job = next(j for j in runs.recent() if j["kind"] == "followup" and j["ref"] == "fu2")
        assert job["status"] == "done"
        assert runs._group("followup") == "tool" and runs._group("regenerate") == "search"
