"""Fake AI provider, search backend and page fetcher for tests and UI development.

    python -m tests.mock          # runs AIRAG on http://localhost:8799 with fake data
"""
from __future__ import annotations
import os

import asyncio
import json
import re

from airag import fetch
from airag.llm import register
from airag.llm.base import LLMProvider
from airag.search import register as register_search
from airag.search.base import SearchBackend, SearchResult

ARTICLE = """# How fast do hummingbird wings beat? Between 10 and 80 times per second
*No single study covers every species, but lab work and field recordings agree that body size is the main factor.*

Most hummingbirds beat their wings **between 10 and 80 times per second** [1][2], with the smallest species at the top of that range [3]. The giant hummingbird manages about 10-15 beats per second [2], while figures above 80 come mostly from enthusiast reports [4].

## What the measurements show

| Species | Beats per second | Source |
|---|---|---|
| Ruby-throated | ~53 | [1] |
| Giant hummingbird | 10-15 | [2] |
| Amethyst woodstar | ~80 | [3] |

## How the sources fit together

The papers measure beats directly with high-speed video, while the forum thread [4] mentions rates in passing.

## Reliability of the evidence

- Lab studies [1][3]: high
- Field guide [2]: good, but rounded
- Forum posts [4]: low

## Caveats and open questions

Courtship dives can briefly push rates much higher [4][9].
"""

HTML = """<!DOCTYPE html><html><head><meta charset="utf-8"><title>Wingbeat</title></head><body style="font-family:system-ui;padding:20px">
<h2>Wingbeat simulator</h2><p>Drag the slider to change body mass.</p><input type="range" id="m" min="2" max="20" value="4">
<p id="o"></p><script>const m=document.getElementById('m'),o=document.getElementById('o');
function u(){o.textContent=Math.round(90-4*m.value)+' beats per second (illustrative)';}m.oninput=u;u();</script></body></html>"""


@register
class MockLLM(LLMProvider):
    name = "mock"
    label = "Mock model"
    fields = [{"key": "model", "label": "Model", "type": "model", "default": "demo"}]
    supports_vision = True

    def vision_content(self, text, image_urls):
        return [{"type": "text", "text": text}, {"type": "image", "n": len(image_urls)}]

    async def complete(self, system, user, max_tokens=2048, json_mode=False):
        await asyncio.sleep(float(os.environ.get('AIRAG_MOCK_DELAY', '0.05')))
        first = user.split("\n")[0].lower()
        if "short tags for this article" in system:
            return '["Hummingbirds", "wing speed", "airag", "birds"]'
        if "planning module" in system:
            return json.dumps({"intent": "How many times per second hummingbird wings beat", "answer_type": "number",
                               "key_terms": ["hummingbird", "wingbeat", "beats per second"],
                               "direct_queries": ["hummingbird wing beats per second"],
                               "related_queries": [{"query": "hummingbird high speed video study", "angle": ""}],
                               "image_query": "hummingbird in flight"})
        if "evaluating ONE source" in system:
            if "none" in first:
                return '{"relevance":1,"coverage":0,"trust":5,"summary":"Nothing relevant.","findings":[]}'
            strong = "results" in first and "page0" in user
            return json.dumps({"relevance": 9 if strong else 6, "coverage": 8 if strong else 3,
                               "source_type": "scientific paper" if strong else "forum thread", "trust": 8 if strong else 5,
                               "trust_reason": "Peer-reviewed measurements." if strong else "Mentions the figure in passing.",
                               "summary": "Reports wingbeat frequencies measured with high-speed cameras.",
                               "findings": [{"claim": "Ruby-throated hummingbirds beat ~53 times/s", "evidence": "53 beats per second",
                                             "directness": "direct"}]})
        if "search strategist" in system:
            return '{"gaps":"species coverage","queries":["giant hummingbird wingbeat frequency"]}'
        if "nothing reliable" in system:
            return ('{"message":"The pages discussed the topic but none had a usable figure.","suggestions":'
                    '[{"query":"hummingbird wingbeat frequency","why":"Standard term"},{"query":"hummingbird flight","why":"Broader"}]}')
        if "interactive simulation" in system:
            return '{"suitable": true, "idea": "A slider that shows how body size changes wingbeat rate.", "reason": "quantitative"}'
        if "interactive explainers" in system:
            return HTML
        if "Turn the reader's formula" in system:
            return "x**2 - 5*x + 6 = 0"
        if "expert translator" in system:   # results page: tag every text so tests can see it was translated
            m = re.search(r">>\n(\[.*\])\n<<", user, re.S)
            items = json.loads(m.group(1)) if m else []
            for it in items:
                it["title"] = "[NB] " + it.get("title", "")
                it["summary"] = "[NB] " + it.get("summary", "")
            return json.dumps({"items": items})
        return "OK"

    async def stream(self, system, user, max_tokens=4096):
        if "look at one picture" in system:
            for piece in ["The picture shows the equation ", "**x² − 5x + 6 = 0**. ", "Its solutions are x = 2 and x = 3."]:
                yield piece
            return
        if "expert translator" in system:
            text = "# Hvor raskt slår kolibrienes vinger?\n\nDe fleste kolibrier slår vingene **10 til 80 ganger i sekundet** [1]."
            for i in range(0, len(text), 40):
                yield text[i:i + 40]
            return
        if "answering follow-ups" in system:
            if "Tool result" not in user and ("calculat" in user.lower() or "how many" in user.lower()):
                yield 'TOOL {"name": "calculator", "args": {"expression": "80 / 10"}}'
                return
            text = ("Larger hummingbirds beat their wings more slowly [2]. The fastest figures come from small species "
                    "[1]." + (" The calculator says the range spans a factor of 8." if "Tool result" in user else ""))
            for i in range(0, len(text), 30):
                await asyncio.sleep(0.005)
                yield text[i:i + 30]
            return
        if "Rewrite the given passage" in system:
            text = "Most hummingbirds flap 10-80 times a second [1]."
            yield text
            return
        if "THIS IS A NEW VERSION" in user:          # Regenerate article
            text = ARTICLE.replace("Most hummingbirds", "Put simply, most hummingbirds", 1)
            for i in range(0, len(text), 40):
                yield text[i:i + 40]
            return
        text = ARTICLE if "research journalist" in system else "**Bottom line:** 10-80 beats per second.\n\n- Smaller birds beat faster [1]\n- Giant hummingbird: 10-15 [2]"
        for i in range(0, len(text), 40):
            await asyncio.sleep(0.005)
            yield text[i:i + 40]


@register_search
class MockSearch(SearchBackend):
    name = "mocksearch"
    label = "Mock search"
    supports_images = True

    async def text(self, q, n=10, recent=""):
        doms = ["nature.com", "allaboutbirds.org", "reddit.com", "pubmed.ncbi.nlm.nih.gov", "audubon.org"]
        return [SearchResult(f"Hummingbird flight study {i}", f"https://{doms[(i + len(q)) % 5]}/{q.replace(' ', '-')}/page{i}",
                             "Measured wingbeat frequency…") for i in range(3)]

    async def images(self, q, n=10):
        return []


async def fake_fetch(url, cfg):
    return fetch.Page(url, final_url=url, ok=True, title="Wingbeat frequency in hummingbirds",
                      text=(url + " hummingbird wingbeat frequency text. ") * 30)


def install(settings_patch: bool = True):
    import airag.fetch as F
    import airag.pipeline as P
    import airag.summarize as Sm
    from airag import config
    F.fetch_page = P.fetch_page = Sm.fetch_page = fake_fetch
    import airag.wikis as W

    async def fake_wikis(wikis, query, n=3, lang="en"):
        return [{"title": "Hummingbird", "url": "https://en.wikipedia.org/wiki/Hummingbird",
                 "snippet": "Hummingbirds are birds native to the Americas", "wiki": "Wikipedia", "trust": 7}]
    W.search_all = fake_wikis
    if settings_patch:
        orig = config.load

        def load(with_env=True):
            s = orig(with_env)
            s["llm"]["provider"] = "mock"
            s["search"]["backend"] = "mocksearch"
            s["search"]["image_backend"] = "none"
            return s
        config.load = load


if __name__ == "__main__":
    install()
    from airag.desktop import launch
    launch(mode="server", port=8799, open_ui=False)
