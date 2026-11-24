"""Quick search: a short cited answer from a few pages, in seconds.

It's the normal research pipeline with a light profile: no AI planning step (the question itself is searched),
one round of at most two searches, 2-3 pages read, a lower relevance bar and a short answer. On an article it can
instead add the answer to the article as a new short section (the old text is kept in Version history).
"""
import re
import time
from typing import List, Optional

from . import history, prompts
from .llm.jsonutil import complete_json
from .pipeline import Research, short_query, tokenize

# the light profile, applied on top of the user's research settings (and again after live settings changes)
PROFILE = {
    "max_rounds": 2,            # round 2 only runs when round 1 found nothing usable
    "sources_per_round": 3,
    "max_sources_total": 6,     # 3 pages, plus 3 more only if the extra searches run
    "max_article_sources": 3,
    "min_findings": 1,
    "use_pinned": False,
    "max_images": 0,
}
MAX_RESULTS = 6          # search results per query
MIN_RELEVANCE = 3        # quick answers accept partly relevant pages (a full search wants 4)
ANSWER_TOKENS = 900
SECTION_TOKENS = 800


class QuickResearch(Research):
    LLM_TASK = "quick"
    def __init__(self, query: str, settings: dict, emit, ui_lang: Optional[str] = None,
                 context_id: Optional[str] = None, update: bool = True, include_library: bool = False):
        ctx = history.get(context_id) if context_id else None
        if context_id and not ctx:
            raise ValueError("That article no longer exists.")
        super().__init__(query, "article", settings, emit, include_library=include_library, ui_lang=ui_lang,
                         extras=False)
        self.context = ctx
        self.into = ctx if (ctx and update and ctx.get("outcome") == "article" and ctx.get("article")) else None
        self.s["search"]["use_wikis"] = False
        self.apply_profile()
        if self.into:
            self.id = self.into["id"]
            self.run_id = self.id + "-quick"

    # settings
    def apply_profile(self) -> None:
        for k, v in PROFILE.items():
            self.r[k] = v
        self.r["results_per_query"] = min(MAX_RESULTS, int(self.r.get("results_per_query") or MAX_RESULTS))

    def refresh_settings(self) -> None:
        super().refresh_settings()
        self.apply_profile()          # live changes never turn a quick search into a full one

    def useful_sources(self) -> List[dict]:
        return [s for s in self.assessed() if s["relevance"] >= MIN_RELEVANCE and s.get("findings")
                and not s.get("_old")]

    # planning without an AI call
    def context_title(self) -> str:
        if not self.context:
            return ""
        return str(self.context.get("title") or self.context.get("query") or "")

    async def make_plan(self) -> None:
        topic = self.context_title()
        queries = [self.query]
        if topic:
            queries.insert(0, short_query(f"{topic} {self.query}"))   # the article's subject keeps the search on topic
        intent = self.query + (f" (a follow-up about: {topic})" if topic else "")
        self.plan = {"intent": intent, "answer_type": "", "key_terms": [], "direct_queries": queries[:2],
                     "related_queries": [], "image_query": "", "freshness": "any", "aspects": [], "quick": True}
        self.terms = list(dict.fromkeys(tokenize(self.query) + tokenize(topic)))
        await self.emit({"type": "plan", "plan": self.plan})
        await self.step("plan", "Quick search", "done", intent)

    # when nothing usable was found: three simpler searches, then the same quick rules
    async def queries_for_round(self, rnd: int) -> List[str]:
        if rnd == 1:
            return await super().queries_for_round(1)
        if rnd != 2 or self.useful_sources():
            return []
        return await self.retry_queries()

    async def retry_queries(self) -> List[str]:
        await self.step("retry", "Nothing usable yet - trying simpler searches")
        try:
            d = await complete_json(self.llm, *prompts.quick_retry(self.query, self.tried, self.context_title()),
                                    max_tokens=300)
            raw = d.get("queries") if isinstance(d, dict) else d
            qs = [" ".join(str(q).split()) for q in (raw or []) if str(q).strip()]
        except Exception as e:
            await self.step("retry", "Couldn't make simpler searches", "warn", str(e)[:160])
            return []
        seen = {t.lower() for t in self.tried}
        qs = [q for q in dict.fromkeys(qs) if q.lower() not in seen][:3]
        await self.step("retry", "Trying simpler searches", "done", " · ".join(qs))
        return qs

    # writing
    def chosen(self) -> List[dict]:
        return sorted(self.useful_sources(), key=self.score, reverse=True)[: int(self.r["max_article_sources"])]

    async def write_article(self, images: List[dict]) -> dict:
        chosen = self.chosen()
        for n, s in enumerate(chosen, 1):
            s["n"] = n
        art_sources = [self.pub(s) for s in chosen]
        await self.step("write", "Writing a quick answer", "running", f"From {len(chosen)} sources")
        await self.emit({"type": "outcome", "outcome": "article"})
        await self.emit({"type": "article_start", "sources": art_sources, "images": [], "related": []})
        md = ""
        async for piece in self.llm.stream(*prompts.quick_answer(self.query, chosen, self.lang, self.context_title()),
                                           max_tokens=ANSWER_TOKENS):
            md += piece
            await self.emit({"type": "token", "text": piece})
        clean = re.sub(r"<think>.*?</think>", "", md, flags=re.S)
        m = re.search(r"^#\s+(.+)$", clean, re.M)
        await self.step("write", "Wrote a quick answer", "done", f"{len(clean.split())} words from {len(chosen)} sources")
        out = {"outcome": "article", "article": md, "article_sources": art_sources, "related": [],
               "title": m.group(1).strip() if m else self.query, "interactive": None, "quick": True}
        if self.context:
            out["quick_of"] = self.context["id"]
        return out

    # adding to an article
    async def run(self) -> dict:
        if not self.into:
            return await super().run()
        t0 = time.time()
        await self.emit({"type": "start", "id": self.run_id, "query": self.query, "mode": "article",
                         "model": self.llm.describe(), "search": self.search.label if self.use_web else "Library only",
                         "created": self.created, "library": self.use_library, "dates": None})
        return await self.run_into(t0)

    async def run_into(self, t0: float) -> dict:
        rec = self.into
        known = {s.get("url") for s in (rec.get("article_sources") or []) if s.get("url")}
        for url in known:                       # the article's own sources aren't read again
            self.sources[url] = {"url": url, "id": self.next_id(), "_old": True, "status": "done", "relevance": None}
            self.order.append(url)
        await self.make_plan()
        if self.use_library:
            await self.library_round()
        if self.use_web:
            fresh = await self.search_round(1, self.plan["direct_queries"])
            await self.read_round(1, fresh)
            if not self.useful_sources():
                self.refresh_settings()
                retry = await self.retry_queries()
                if retry:
                    await self.read_round(2, await self.search_round(2, retry))
        chosen = self.chosen()
        old_art = list(rec.get("article_sources") or [])
        section = ""
        if chosen:
            first = max([int(x.get("n") or 0) for x in old_art] + [0]) + 1
            for i, s in enumerate(chosen):
                s["n"] = first + i
            await self.step("write", "Adding the quick answer to the article", "running", f"{len(chosen)} new sources")
            async for piece in self.llm.stream(*prompts.quick_section(self.query, rec.get("article") or "", chosen,
                                                                      self.lang), max_tokens=SECTION_TOKENS):
                section += piece
            section = re.sub(r"<think>.*?</think>", "", section, flags=re.S).strip()
            await self.step("write", "Added the quick answer to the article", "done", f"{len(chosen)} new sources")
        else:
            await self.step("write", "Nothing useful found", "warn", "The article stays as it was")
        new_sources = [self.pub(s) for s in chosen]
        new_steps = [st for st in self.steps.values() if st["id"] != "plan"]
        record = rec

        def merge(cur: dict) -> None:
            # on top of the saved copy as it is now: anything changed while this ran is kept
            before, before_src = cur.get("article") or "", cur.get("article_sources")
            if section:
                cur["article"] = before.rstrip() + "\n\n" + section + "\n"
                cur["article_sources"] = list(before_src or []) + new_sources
                cur["sources"] = list(cur.get("sources") or []) + [s for s in new_sources
                                                                   if s.get("url") not in {x.get("url") for x in cur.get("sources") or []}]
                from . import versions
                versions.note_change(cur, before, "quick", f"Quick search: {self.query}"[:200], before_src)
            cur["tried"] = list(cur.get("tried") or []) + [q for q in self.tried if q not in (cur.get("tried") or [])]
            cur["steps"] = list(cur.get("steps") or []) + new_steps
            cur["quick_added"] = int(cur.get("quick_added") or 0) + (1 if section else 0)
        try:
            saved = history.update(self.id, merge)
            if saved is not None:
                record = saved
        except OSError as e:
            self.warnings.append(f"Couldn't save history: {e}")
        await self.emit({"type": "done", "id": self.id, "elapsed": round(time.time() - t0, 1), "outcome": "article",
                         "extended": len(new_sources), "quick": True})
        return record
