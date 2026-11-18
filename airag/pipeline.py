"""The research agent.

1. Plan: work out the intent and write direct + related search queries.
2. Round 1 searches directly, reads the top pages and has the AI assess each one.
   If a page is relevant and thorough enough, show ranked results.
3. Round 2 searches related/indirect sources, rounds 3+ fill gaps the AI points out.
4. Enough findings -> write a cited article (streamed). Nothing usable -> suggest searches.

Each stage is a method, so it's easy to override or extend. Progress goes to the
browser as events through `emit`.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import re
import time
from pathlib import Path
from typing import Awaitable, Callable, Dict, List, Optional
from urllib.parse import urldefrag, urlparse

from copy import deepcopy

from . import guard, history, languages, prompts
from .fetch import fetch_page
from .library import LIBRARY, settings_args as library_args
from .llm import LLMError, get_llm
from .llm.jsonutil import complete_json
from .passages import select_passages, tokenize
from .search import SearchError, get_image_search, get_search
from .trust import domain_prior

Emit = Callable[[dict], Awaitable[None]]

PUBLIC_KEYS = ("id", "n", "url", "domain", "title", "snippet", "query", "round", "status", "relevance", "coverage",
               "trust", "trust_reason", "source_type", "summary", "findings", "prior", "prior_label", "published",
               "author", "site_name", "og_image", "error", "via", "date", "local", "path", "file_id", "suspicious",
               "out_of_range", "pinned")


def domain_of(url: str) -> str:
    d = urlparse(url).netloc.lower().split(":")[0]
    return d[4:] if d.startswith("www.") else d


def _clamp(v, lo=0, hi=10) -> Optional[int]:
    try:
        return max(lo, min(hi, int(round(float(v)))))
    except (TypeError, ValueError):
        return None


_MONTHS = {m: i for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov",
                                       "dec"), 1)}
_MONTHS.update({"mai": 5, "okt": 10, "des": 12, "dez": 12, "mär": 3, "mrz": 3, "maj": 5})   # nb/sv/da/de


def page_date_span(text: str) -> Optional[tuple]:
    """Earliest and latest ISO day a date string can mean: '2026-11-03' -> (that day, that day),
    'November 2026' -> the whole month, '2025' -> the whole year. None if no date is found."""
    import calendar
    t = str(text or "").lower()
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", t)
    if m:
        y, mo, d = map(int, m.groups())
        if 1 <= mo <= 12 and 1 <= d <= 31:
            day = f"{y:04d}-{mo:02d}-{d:02d}"
            return day, day
    m = re.search(r"(\d{1,2})\.?\s+([a-z]{3})[a-z]*\.?,?\s+(\d{4})", t) or \
        re.search(r"([a-z]{3})[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})", t)
    if m:
        a, b, y = m.groups()
        mon, day = (b, a) if a.isdigit() else (a, b)
        if mon[:3] in _MONTHS:
            iso = f"{int(y):04d}-{_MONTHS[mon[:3]]:02d}-{int(day):02d}"
            return iso, iso
    m = re.search(r"([a-z]{3})[a-z]*\s+(\d{4})", t) or re.search(r"(\d{4})-(\d{1,2})(?!\d)", t)
    if m:
        a, b = m.groups()
        if a.isdigit():
            y, mo = int(a), int(b)
        elif a[:3] in _MONTHS:
            y, mo = int(b), _MONTHS[a[:3]]
        else:
            y = mo = 0
        if y and 1 <= mo <= 12:
            last = calendar.monthrange(y, mo)[1]
            return f"{y:04d}-{mo:02d}-01", f"{y:04d}-{mo:02d}-{last:02d}"
    m = re.search(r"\b(19\d{2}|20\d{2})\b", t)
    if m:
        y = int(m.group(1))
        return f"{y}-01-01", f"{y}-12-31"
    return None


def _slug(text: str) -> str:
    return re.sub(r"[^\w]+", "-", text.lower(), flags=re.UNICODE).strip("-_")[:40] or "search"


class Research:
    def __init__(self, query: str, mode: str, settings: dict, emit: Emit,
                 include_library: bool = False, ui_lang: Optional[str] = None, from_id: Optional[str] = None,
                 date_from: str = "", date_to: str = "", merge_id: Optional[str] = None, extras: bool = True,
                 extend_id: Optional[str] = None):
        self.extend = history.get(extend_id) if extend_id else None   # "Locate more sources" for this article
        if self.extend and (self.extend.get("outcome") != "article" or not self.extend.get("plan")):
            raise ValueError("More sources can only be added to a finished article.")
        if self.extend:
            from_id = merge_id = None
            query = self.extend["query"]
        self.prev = history.get(from_id) if from_id else None   # reuse the sources of an earlier search
        self.merge = history.get(merge_id) if merge_id and not from_id else None   # search again, keep old sources
        if self.prev and self.prev.get("query"):
            query = self.prev["query"]
        self.query = " ".join(query.split())
        self.extras = bool(extras)   # pictures + interactive explainer check (off = fewer tokens)
        from .search.base import date_range
        self.dates = date_range(f"{date_from or ''}..{date_to or ''}") if (date_from or date_to) else None
        if not self.query:
            raise ValueError("Empty search")
        self.mode = mode if mode in ("auto", "article", "results") else "auto"
        settings = deepcopy(settings)
        self.ui_lang = languages.normalize(ui_lang) or "en"
        self.lang = languages.answer_language(settings, self.ui_lang, self.query)
        ans = settings["app"].get("answer_language", "auto")
        lang_code = languages.normalize(ans) or (self.ui_lang if ans == "ui" else None)
        if str(settings["search"].get("region", "auto")).lower() == "auto":
            settings["search"]["region"] = languages.region(lang_code or self.ui_lang)
        settings["fetch"]["accept_language"] = f"{lang_code or self.ui_lang},en;q=0.8"
        self.s = settings
        self.r = settings["research"]
        self.use_library = bool(include_library) and bool(library_args(settings)["folders"])
        self.use_web = (not self.use_library) or bool(settings["library"].get("web_too", True))
        self.emit = emit
        self.llm = get_llm(settings)
        self.search = get_search(settings)
        self.img_search = get_image_search(settings)
        self.sources: Dict[str, dict] = {}
        self.order: List[str] = []
        self._last_id = 0
        self.tried: List[str] = []
        self.plan: dict = {}
        self.terms: List[str] = []
        self.steps: Dict[str, dict] = {}
        self.read_count = 0
        self.warnings: List[str] = []
        now = dt.datetime.now()
        self.id = self.extend["id"] if self.extend else now.strftime("%Y%m%d-%H%M%S-") + _slug(self.query)
        self.run_id = self.id      # the background job's id (differs when extending an article)
        self.created = now.astimezone().isoformat(timespec="seconds")
        self.skip = [d.strip().lower() for d in str(self.r.get("skip_domains", "")).split(",") if d.strip()]
        self._sem_llm = asyncio.Semaphore(max(1, int(self.r["llm_concurrency"])))
        self._sem_fetch = asyncio.Semaphore(max(1, int(settings["fetch"]["max_concurrency"])))
        self._texts: Dict[str, set] = {}   # url -> five-word runs of its text, to spot copies of the same article

    # helpers
    async def step(self, sid: str, label: str, status: str = "running", detail: str = "") -> None:
        self.steps[sid] = {"id": sid, "label": label, "status": status, "detail": detail}
        await self.emit({"type": "step", **self.steps[sid]})

    def next_id(self) -> int:
        """Source numbers stay unique even when irrelevant library files are dropped from the list."""
        self._last_id += 1
        return self._last_id

    def pub(self, s: dict) -> dict:
        return {k: s.get(k) for k in PUBLIC_KEYS if k in s}

    async def emit_source(self, s: dict) -> None:
        if s.get("_quiet"):      # a library file still being checked: only shown once it's relevant
            return
        await self.emit({"type": "source", "source": self.pub(s)})

    def assessed(self) -> List[dict]:
        return [self.sources[u] for u in self.order
                if self.sources[u].get("relevance") is not None and not self.sources[u].get("out_of_range")]

    def check_dates(self, s: dict) -> None:
        """With a date range picked, leave out pages whose date is clearly outside it
        (search engines don't all support date filters, and the ones that do aren't exact)."""
        if not self.dates:
            return
        span = page_date_span(s.get("published") or "") or page_date_span(s.get("date") or "")
        if span and (span[1] < self.dates[0] or span[0] > self.dates[1]):
            s["out_of_range"] = True

    @staticmethod
    def score(s: dict) -> float:
        return (s.get("relevance") or 0) * 0.5 + (s.get("coverage") or 0) * 0.3 + (s.get("trust") or 0) * 0.2

    def strong_matches(self) -> List[dict]:
        return [s for s in self.assessed()
                if s["relevance"] >= int(self.r["direct_relevance"]) and (s.get("coverage") or 0) >= int(self.r["direct_coverage"])]

    def useful_sources(self) -> List[dict]:
        return [s for s in self.assessed() if s["relevance"] >= 4 and s.get("findings")]

    def useful_findings(self) -> List[dict]:
        return [f for s in self.useful_sources() for f in s["findings"]]

    def enough_material(self) -> bool:
        fs = self.useful_findings()
        has_direct = any(f.get("directness") == "direct" for s in self.useful_sources() if s["relevance"] >= 6
                         for f in s["findings"])
        return len(fs) >= int(self.r["enough_findings"]) and has_direct

    # main flow
    async def run(self) -> dict:
        t0 = time.time()
        await self.emit({"type": "start", "id": self.run_id, "query": self.query, "mode": self.mode,
                         "model": self.llm.describe(), "search": self.search.label if self.use_web else "Library only",
                         "created": self.created, "library": self.use_library,
                         "dates": list(self.dates) if self.dates else None})
        if self.extend:
            return await self.run_extend(t0)
        if self.prev and self.prev.get("plan") and self.prev.get("sources"):
            return await self.run_from_previous(t0)
        try:
            return await self.run_search(t0)
        except Exception as e:
            self.save_failed(e, t0)   # keep what was found, so "Search again" can build on it
            raise

    def save_failed(self, err: Exception, t0: float) -> None:
        if not self.order or not self.plan:
            return
        record = self.base_record([])
        record.update({"outcome": "error", "error": str(err)[:500], "steps": list(self.steps.values()),
                       "sources": [self.pub(self.sources[u]) for u in self.order],
                       "elapsed": round(time.time() - t0, 1), "warnings": self.warnings})
        try:
            history.save(record, int(self.s["app"].get("history_limit", 300)))
        except OSError:
            pass

    def seed_from_merge(self) -> int:
        """Sources from the earlier search that were read and judged; new searches add to them."""
        n = 0
        for src in (self.merge or {}).get("sources") or []:
            if src.get("relevance") is None or not src.get("url") or src["url"] in self.sources:
                continue
            s = {k: v for k, v in src.items() if k not in ("excerpt", "n")}
            s.update({"id": self.next_id(), "round": 0, "query": "previous search"})
            self.sources[s["url"]] = s
            self.order.append(s["url"])
            self.check_dates(s)
            n += 1
        return n

    async def run_search(self, t0: float) -> dict:
        await self.make_plan()
        if self.merge:
            n = self.seed_from_merge()
            if n:
                await self.emit({"type": "sources", "items": [self.pub(self.sources[u]) for u in self.order]})
                await self.step("reuse", f"Using {n} sources from the previous search", "done",
                                "New sources found now are compared with these")
        if self.use_library:
            await self.library_round()
        if self.r.get("use_pinned", True):
            await self.pinned_round()

        img_task = None
        if (self.extras and self.use_web and int(self.r.get("max_images", 0)) > 0 and self.img_search
                and self.plan.get("image_query")):
            img_task = asyncio.create_task(self.search_images())

        outcome = None
        for rnd in range(1, (max(1, int(self.r["max_rounds"])) + 1) if self.use_web else 1):
            if self.read_count >= int(self.r["max_sources_total"]):
                break
            queries = await self.queries_for_round(rnd)
            if not queries:
                if rnd > 2:
                    break
                continue
            fresh = await self.search_round(rnd, queries)
            await self.read_round(rnd, fresh)
            if self.mode == "results":
                break
            if self.mode == "auto" and self.strong_matches():
                outcome = "results"
                break
            if self.enough_material():
                break

        searched_images = []
        if img_task:
            try:
                searched_images = await img_task
            except Exception:
                searched_images = []
        images = await self.choose_images(self.collect_images(searched_images)) if self.extras else []

        record = self.base_record(images)
        if self.mode == "results" or outcome == "results":
            record.update(await self.show_results(images))
        elif len(self.useful_findings()) >= int(self.r["min_findings"]) or (self.mode == "article" and self.useful_sources()):
            record.update(await self.write_article(images))
        else:
            record.update(await self.suggest())
        return await self.finish(record, t0)

    def base_record(self, images: List[dict]) -> dict:
        return {"id": self.id, "query": self.query, "mode": self.mode, "created": self.created,
                "model": self.llm.describe(), "search": self.search.label, "plan": self.plan,
                "tried": self.tried, "images": images, "library": self.use_library, "web": self.use_web,
                "language": self.lang, "dates": list(self.dates) if self.dates else None, "extras": self.extras}

    async def finish(self, record: dict, t0: float) -> dict:
        record["steps"] = list(self.steps.values())
        record["sources"] = [self.pub(self.sources[u]) for u in self.order]
        record["elapsed"] = round(time.time() - t0, 1)
        record["warnings"] = self.warnings
        try:
            history.save(record, int(self.s["app"].get("history_limit", 300)))
        except OSError as e:
            self.warnings.append(f"Couldn't save history: {e}")
        await self.emit({"type": "done", "id": self.id, "elapsed": record["elapsed"], "outcome": record["outcome"]})
        return record

    async def run_from_previous(self, t0: float) -> dict:
        """Write an article from the sources an earlier search already found ("Write an article anyway"):
        no new planning or searching. Pages already assessed are re-opened (usually from the cache) to get
        their text back; if that isn't enough material, the best unread results are read too."""
        p = self.prev
        self.mode = "article"
        self.extras = p.get("extras", True) is not False
        if not self.dates and p.get("dates"):
            self.dates = tuple(p["dates"])
        self.plan = p["plan"]
        self.terms = list(dict.fromkeys(tokenize(self.query) + tokenize(" ".join(self.plan.get("key_terms") or []))))
        self.tried = list(p.get("tried") or [])
        self.use_library = bool(p.get("library"))
        await self.emit({"type": "plan", "plan": self.plan})
        n = len(p["sources"])
        await self.step("plan", "Understanding the question", "done", self.plan.get("intent", ""))
        for src in p["sources"]:
            s = {k: v for k, v in src.items() if k != "excerpt"}
            s["id"] = self.next_id()
            self.sources[s["url"]] = s
            self.order.append(s["url"])
        await self.emit({"type": "sources", "items": [self.pub(self.sources[u]) for u in self.order]})
        await self.step("reuse", f"Using {n} sources from the previous search", "done", "")

        known = [s for s in self.useful_sources()]
        if known:
            await self.step("reopen", f"Re-opening {len(known)} pages", "running", ", ".join(s["domain"] for s in known))
            await asyncio.gather(*(self.reopen(s) for s in known))
            await self.step("reopen", f"Re-opened {len(known)} pages", "done", "")
        if len(self.useful_findings()) < int(self.r["min_findings"]):
            unread = [self.sources[u] for u in self.order if self.sources[u].get("status") == "found"]
            unread.sort(key=lambda x: (x.get("round") or 9, x.get("rank") or 0))
            await self.read_round(1, unread)
        record = self.base_record(p.get("images") or [])
        if self.useful_sources():
            record.update(await self.write_article(record["images"]))
        else:
            record.update(await self.suggest())
        return await self.finish(record, t0)

    async def run_extend(self, t0: float) -> dict:
        """"Locate more sources": search for sources the article doesn't have yet, read them, and add a section
        with what they contribute. The article itself is kept as it is (same history entry, updated)."""
        rec = self.extend
        self.mode = "article"
        self.extras = False
        if not self.dates and rec.get("dates"):
            self.dates = tuple(rec["dates"])
        self.plan = rec["plan"]
        self.terms = list(dict.fromkeys(tokenize(self.query) + tokenize(" ".join(self.plan.get("key_terms") or []))))
        self.tried = list(rec.get("tried") or [])
        self.use_library = bool(rec.get("library"))
        await self.emit({"type": "plan", "plan": self.plan})
        await self.step("plan", "Understanding the question", "done", self.plan.get("intent", ""))
        known = set()
        for src in rec.get("sources") or []:       # already known: not searched or read again
            if src.get("url"):
                s = {k: v for k, v in src.items() if k not in ("excerpt", "n")}
                s["id"] = self.next_id()
                s["_old"] = True
                self.sources[s["url"]] = s
                self.order.append(s["url"])
                known.add(s["url"])
        await self.emit({"type": "sources", "items": [self.pub(self.sources[u]) for u in self.order]})
        await self.step("reuse", f"The article already uses {len(rec.get('article_sources') or [])} sources", "done",
                        "Looking for new ones")
        before = len(self.useful_sources())
        for rnd in range(3, 3 + max(1, int(self.r["max_rounds"]))):     # new angles only (rounds 1-2 were done)
            queries = await self.queries_for_round(rnd)
            if not queries:
                break
            fresh = await self.search_round(rnd, queries)
            await self.read_round(rnd, fresh)
            if len(self.useful_sources()) - before >= 4:
                break
        new = sorted([s for s in self.useful_sources() if not s.get("_old")], key=self.score, reverse=True)[:6]
        old_art = list(rec.get("article_sources") or [])
        record = dict(rec)
        record["tried"] = self.tried
        if new:
            first = max([int(x.get("n") or 0) for x in old_art] + [0]) + 1
            for i, s in enumerate(new):
                s["n"] = first + i
            await self.step("write", "Adding what the new sources say", "running", f"{len(new)} new sources")
            md = ""
            async for piece in self.llm.stream(*prompts.addendum(self.query, rec.get("article") or "", new, self.lang),
                                               max_tokens=1600):
                md += piece
            md = re.sub(r"<think>.*?</think>", "", md, flags=re.S).strip()
            record["article"] = (rec.get("article") or "").rstrip() + "\n\n" + md + "\n"
            record["article_sources"] = old_art + [self.pub(s) for s in new]
            await self.step("write", "Added what the new sources say", "done", f"{len(new)} new sources")
        else:
            await self.step("write", "No new useful sources found", "warn", "The article stays as it was")
        record["sources"] = [self.pub(self.sources[u]) for u in self.order]
        record["steps"] = list(rec.get("steps") or []) + [st for st in self.steps.values() if st["id"] not in ("plan",)]
        record["more_sources"] = int(rec.get("more_sources") or 0) + len(new)
        try:
            history.save(record, int(self.s["app"].get("history_limit", 300)))
        except OSError as e:
            self.warnings.append(f"Couldn't save history: {e}")
        await self.emit({"type": "done", "id": self.id, "elapsed": round(time.time() - t0, 1), "outcome": "article",
                         "extended": len(new)})
        return record

    async def reopen(self, s: dict) -> None:
        """Get an assessed source's text back for the article writer (no new AI assessment)."""
        try:
            if s.get("local"):
                from .library import allowed_file, extract
                if not s.get("path") or not allowed_file(s["path"], self.s):
                    return
                text = await asyncio.to_thread(extract, Path(s["path"]))
            else:
                async with self._sem_fetch:
                    page = await fetch_page(s["url"], self.s["fetch"])
                if not page.ok:
                    return
                text = page.text
            excerpt, suspicious = guard.clean(select_passages(text, self.terms, int(self.r["passage_chars"])), self.s)
            s["excerpt"] = excerpt
            if suspicious:
                s["suspicious"] = True
        except Exception:
            pass  # the findings and summary from the first search are still used

    # stages
    async def make_plan(self) -> None:
        await self.step("plan", "Understanding the question")
        try:
            d = await complete_json(self.llm, *prompts.plan(self.query, self.use_web, self.use_library), max_tokens=1200)
        except LLMError:
            raise
        except Exception as e:
            raise LLMError(f"Planning failed: {e}")

        def strs(v) -> List[str]:
            return [str(x).strip() for x in (v or []) if str(x).strip()] if isinstance(v, list) else []

        direct = strs(d.get("direct_queries"))
        if self.query.lower() not in (q.lower() for q in direct):
            direct.insert(0, self.query)
        related = []
        for x in d.get("related_queries") or []:
            if isinstance(x, dict) and x.get("query"):
                related.append({"query": str(x["query"]).strip(), "angle": str(x.get("angle", "")).strip()})
            elif isinstance(x, str) and x.strip():
                related.append({"query": x.strip(), "angle": ""})
        self.plan = {
            "intent": str(d.get("intent") or self.query).strip(),
            "answer_type": str(d.get("answer_type") or "").strip(),
            "key_terms": strs(d.get("key_terms"))[:16],
            "direct_queries": direct[:4],
            "related_queries": related[:6],
            "image_query": str(d.get("image_query") or "").strip(),
            "freshness": str(d.get("freshness") or "any").strip(),
        }
        self.terms = list(dict.fromkeys(tokenize(self.query) + tokenize(" ".join(self.plan["key_terms"]))))
        await self.emit({"type": "plan", "plan": self.plan})
        await self.step("plan", "Understanding the question", "done", self.plan["intent"])

    async def library_round(self) -> None:
        """Search the user's local library (Retrieve & Get)."""
        await self.step("library", "Searching your library")
        lib = self.s["library"]
        try:
            if time.time() - LIBRARY.last_sync() > 300:  # refresh index (only changed files are re-read)
                await asyncio.to_thread(LIBRARY.sync, **library_args(self.s))
            queries = self.plan["direct_queries"] + [" ".join(self.plan["key_terms"]), self.query]
            hits = await asyncio.to_thread(LIBRARY.search, queries, int(lib.get("max_results", 6)),
                                           int(self.r["passage_chars"]))
        except Exception as e:
            await self.step("library", "Searching your library", "warn", f"Library error: {e}"[:200])
            return
        from .library import allowed_file
        fresh = []
        for h in hits:
            url = f"/api/library/file/{h['file_id']}"
            if url in self.sources or not allowed_file(h["path"], self.s):
                continue
            root_name = Path(h["root"]).name or h["root"]
            src = {"id": self.next_id(), "url": url, "domain": "library", "title": h["title"],
                   "snippet": h["excerpt"][:240], "query": "library", "round": 0, "rank": len(fresh), "status": "found",
                   "prior": int(lib.get("trust", 6)), "prior_label": f"Your library ({root_name})",
                   "local": True, "path": h["path"], "file_id": h["file_id"], "_text": h["excerpt"],
                   "site_name": root_name, "_quiet": True}
            self.sources[url] = src
            self.order.append(url)
            fresh.append(src)
        if fresh:
            await asyncio.gather(*(self.read_one(x) for x in fresh))
        # Only library files that are relevant enough to this question are listed and used
        min_rel = int(lib.get("min_relevance", 4))
        useful = [x for x in fresh if (x.get("relevance") or 0) >= min_rel and x.get("findings")]
        for x in fresh:
            x.pop("_quiet", None)
            if x not in useful:
                self.order.remove(x["url"])          # stays in self.sources so it isn't added again
        if useful:
            await self.emit({"type": "sources", "items": [self.pub(x) for x in useful]})
        useful = len(useful)
        await self.step("library", "Searched your library", "done",
                        f"{len(fresh)} matching files checked · {useful} relevant" if fresh else "No matching files")

    async def pinned_round(self) -> None:
        """Pinned sources that match the question are read from their saved copy first."""
        from . import pinned
        try:
            hits = await asyncio.to_thread(pinned.matching, self.terms)
        except Exception:
            return
        fresh = []
        for h in hits:
            if h["url"] in self.sources:
                continue
            src = {"id": self.next_id(), "url": h["url"], "domain": h.get("domain") or domain_of(h["url"]),
                   "title": h.get("title") or h["url"], "snippet": (h.get("summary") or "")[:240], "query": "pinned",
                   "round": 0, "rank": len(fresh), "status": "found", "prior": 8, "prior_label": "Pinned by you",
                   "pinned": True, "_text": h.get("text", ""), "published": h.get("published"),
                   "site_name": h.get("site_name")}
            self.sources[h["url"]] = src
            self.order.append(h["url"])
            fresh.append(src)
        if not fresh:
            return
        await self.step("pinned", "Reading your pinned sources", "running", f"{len(fresh)} match this search")
        await self.emit({"type": "sources", "items": [self.pub(x) for x in fresh]})
        await asyncio.gather(*(self.read_one(x) for x in fresh))
        useful = sum(1 for x in fresh if (x.get("relevance") or 0) >= 4)
        await self.step("pinned", "Read your pinned sources", "done", f"{len(fresh)} checked · {useful} relevant")

    async def queries_for_round(self, rnd: int) -> List[str]:
        if rnd == 1:
            qs = self.plan["direct_queries"]
        elif rnd == 2:
            qs = [q["query"] for q in self.plan["related_queries"]]
        else:
            qs = await self.refine_queries(rnd)
        seen = {t.lower() for t in self.tried}
        out = []
        for q in qs:
            q = " ".join(str(q).split())
            if q and q.lower() not in seen:
                seen.add(q.lower())
                out.append(q)
        return out[:5]

    async def refine_queries(self, rnd: int) -> List[str]:
        await self.step(f"refine{rnd}", "Looking for gaps")
        claims = [f.get("claim", "") for f in self.useful_findings()]
        try:
            d = await complete_json(self.llm, *prompts.refine(self.query, self.plan["intent"], self.tried, claims), max_tokens=800)
            qs = [str(q) for q in d.get("queries") or [] if str(q).strip()]
            await self.step(f"refine{rnd}", "Looking for gaps", "done", str(d.get("gaps", ""))[:200])
            return qs
        except Exception as e:
            await self.step(f"refine{rnd}", "Looking for gaps", "warn", str(e)[:160])
            return []

    def _skipped(self, domain: str) -> bool:
        return any(domain == d or domain.endswith("." + d) for d in self.skip)

    async def search_round(self, rnd: int, queries: List[str]) -> List[dict]:
        self.tried += queries
        sid = f"search{rnd}"
        label = {1: "Searching the web", 2: "Searching related sources"}.get(rnd, "Searching for missing pieces")
        await self.step(sid, label, "running", " · ".join(queries))
        n = int(self.r["results_per_query"])

        # news and "latest" questions: ask the search engine for recent pages first
        fresh = self.plan.get("freshness", "any")
        if self.dates:   # the reader picked a date range: every search is limited to it
            recent = "..".join(self.dates)
        else:
            recent = {"latest": "week", "recent": "year"}.get(fresh, "") if rnd == 1 or fresh == "latest" else ""

        async def one(q):
            try:
                res = await self.search.text(q, n, recent=recent) if recent else []
                if len(res) < 3 and not self.dates:   # too narrow (or no time filter): search all dates too
                    seen = {r.url for r in res}
                    res += [r for r in await self.search.text(q, n) if r.url not in seen]
                return q, res
            except Exception as e:
                return q, e

        results = await asyncio.gather(*(one(q) for q in queries))
        lists, errors = [], []
        for q, res in results:
            if isinstance(res, Exception):
                errors.append(f"{q}: {res}")
            else:
                lists.append((q, res))
        if errors and not lists and rnd == 1:
            raise SearchError("Web search failed - " + errors[0])
        fresh: List[dict] = []
        depth = max((len(r) for _, r in lists), default=0)
        for i in range(depth):  # interleave by rank across queries
            for q, res in lists:
                if i >= len(res):
                    continue
                item = res[i]
                url = urldefrag(item.url)[0]
                if not url.startswith(("http://", "https://")) or url in self.sources:
                    continue
                dom = domain_of(url)
                if self._skipped(dom):
                    continue
                prior, prior_label = domain_prior(dom)
                src = {"id": self.next_id(), "url": url, "domain": dom, "title": item.title, "snippet": item.snippet,
                       "query": q, "round": rnd, "rank": i, "status": "found", "prior": prior, "prior_label": prior_label}
                self.sources[url] = src
                self.order.append(url)
                fresh.append(src)
        if fresh:
            await self.emit({"type": "sources", "items": [self.pub(s) for s in fresh]})
        detail = f"{len(fresh)} new pages from {len(queries)} searches"
        if errors:
            detail += f" · {len(errors)} failed"
            self.warnings += errors
        await self.step(sid, label, "warn" if errors else "done", detail)
        return fresh

    async def read_round(self, rnd: int, fresh: List[dict]) -> None:
        budget = int(self.r["max_sources_total"]) - self.read_count
        to_read = fresh[: max(0, min(int(self.r["sources_per_round"]), budget))]
        if not to_read:
            return
        self.read_count += len(to_read)
        sid = f"read{rnd}"
        await self.step(sid, f"Reading {len(to_read)} pages", "running", ", ".join(s["domain"] for s in to_read))
        await asyncio.gather(*(self.read_one(s) for s in to_read))
        useful = sum(1 for s in to_read if (s.get("relevance") or 0) >= 4 and s.get("findings"))
        unread = sum(1 for s in to_read if s["status"] in ("unreadable", "error"))
        detail = f"{useful} contained relevant information"
        if unread:
            detail += f" · {unread} couldn't be read"
        await self.step(sid, f"Read {len(to_read)} pages", "done", detail)

    async def read_one(self, s: dict) -> None:
        if s.get("local"):
            excerpt = s.pop("_text", "")
            s["via"] = "library"
        elif s.get("pinned") and s.get("_text"):     # pinned page: its saved copy, no fetching
            text = s.pop("_text")
            s["via"] = "pinned"
            excerpt = select_passages(text, list(self.search_terms()), self.excerpt_budget(text))
        else:
            async with self._sem_fetch:
                s["status"] = "reading"
                await self.emit_source(s)
                page = await fetch_page(s["url"], self.s["fetch"])
            s["via"] = page.via
            if not page.ok or len(page.text.strip()) < 120:
                s["status"] = "unreadable"
                s["error"] = page.error or "Too little text"
                await self.emit_source(s)
                return
            s.update({k: v for k, v in {"title": page.title or s["title"], "published": page.published,
                                        "author": page.author, "site_name": page.site_name,
                                        "og_image": page.og_image}.items() if v})
            if page.scholarly:
                s["prior"], s["prior_label"] = domain_prior(s["domain"], scholarly=True)
            s["_images"] = page.images
            if await self.skip_without_ai(s, page.text):
                return
            excerpt = select_passages(page.text, list(self.search_terms()), self.excerpt_budget(page.text))
        excerpt, suspicious = guard.clean(excerpt, self.s)
        if suspicious:
            s["suspicious"] = True
        s["status"] = "assessing"
        await self.emit_source(s)
        s["excerpt"] = excerpt
        async with self._sem_llm:
            try:
                a = await complete_json(self.llm, *prompts.assess(
                    self.query, self.plan["intent"], s["title"], s["url"], s["prior"], s["prior_label"], excerpt,
                    local=bool(s.get("local")), freshness=self.plan.get("freshness", "any"),
                    published=s.get("published") or "", dates=self.dates), max_tokens=1600)
            except Exception as e:
                s["status"] = "error"
                s["error"] = f"AI assessment failed: {e}"[:200]
                await self.emit_source(s)
                return
        findings = []
        for f in a.get("findings") or []:
            if isinstance(f, dict) and str(f.get("claim", "")).strip():
                findings.append({"claim": str(f["claim"]).strip(), "evidence": str(f.get("evidence", "")).strip()[:300],
                                 "directness": str(f.get("directness", "")).strip().lower()})
            elif isinstance(f, str) and f.strip():
                findings.append({"claim": f.strip(), "evidence": "", "directness": ""})
        s.update({
            "relevance": _clamp(a.get("relevance")) or 0,
            "coverage": _clamp(a.get("coverage")) or 0,
            "trust": max(0, (_clamp(a.get("trust")) if _clamp(a.get("trust")) is not None else s["prior"])
                         - (3 if s.get("suspicious") else 0)),
            "trust_reason": str(a.get("trust_reason") or s["prior_label"]).strip(),
            "source_type": str(a.get("source_type") or "").strip(),
            "summary": str(a.get("summary") or "").strip(),
            "findings": findings[:8],
            "date": str(a.get("date") or "").strip()[:40],
            "status": "assessed",
        })
        self.check_dates(s)
        await self.emit_source(s)

    @staticmethod
    def _shingles(text: str) -> set:
        words = re.findall(r"\w+", text[:8000].lower())
        return {" ".join(words[i:i + 5]) for i in range(0, max(0, len(words) - 4))}

    def search_terms(self) -> set:
        """Key words from the question, the planner's key terms and every search the AI ran."""
        terms = set(self.terms)
        for q in self.tried:
            terms.update(tokenize(q))
        return terms

    async def skip_without_ai(self, s: dict, text: str) -> bool:
        """Skip the AI only for copies of a page already read (syndicated news, mirrors). Copies are found by
        comparing overlapping five-word runs of the text (no tokens used): pages that share most of their wording
        count as the same article, while pages that only quote each other or share a template don't."""
        sh = self._shingles(text)
        if len(sh) >= 60:
            for url, other in self._texts.items():
                if url != s["url"] and len(sh & other) / len(sh | other) >= 0.8:
                    s.update({"status": "assessed", "relevance": 0, "coverage": 0, "trust": s["prior"], "findings": [],
                              "summary": "Same text as another source.", "trust_reason": s["prior_label"],
                              "duplicate_of": url})
                    await self.emit_source(s)
                    return True
            self._texts[s["url"]] = sh
        return False

    def excerpt_budget(self, text: str) -> int:
        """Full reading budget for pages that use the search's key words; a short read for pages that don't
        (they still get looked at - a research agent can find useful facts in unexpected places)."""
        full = int(self.r["passage_chars"])
        words = set(tokenize(text[:200000]))
        terms = self.search_terms()
        if terms and not any(t in words for t in terms):
            return min(full, 900)
        return full

    # images
    async def search_images(self) -> List[dict]:
        q = self.plan.get("image_query") or ""
        res = await self.img_search.images(q, int(self.r["max_images"]) * 2)
        out = []
        for i in res:
            if (i.width and i.width < 200) or (i.height and i.height < 150):
                continue
            out.append({"src": i.image, "thumb": i.thumbnail or i.image, "page_url": i.page_url or i.image,
                        "title": i.title, "credit": domain_of(i.page_url or i.image), "origin": "image search"})
        return out

    def collect_images(self, searched: List[dict]) -> List[dict]:
        if not self.plan.get("image_query"):
            return []  # the planner decided pictures wouldn't help
        out, seen = [], set()

        def add(img: dict) -> None:
            if img["src"] and img["src"] not in seen:
                seen.add(img["src"])
                out.append(img)

        terms = set(self.terms)
        limit = int(self.r["max_images"])
        from_sources: List[dict] = []
        for s in sorted(self.assessed(), key=self.score, reverse=True):
            if s["relevance"] < 5:
                continue
            for im in s.get("_images") or []:  # in-article images whose alt/caption match the topic
                words = set(tokenize(im.get("alt", "") + " " + im.get("caption", "")))
                if len(words & terms) >= 1:
                    from_sources.append({"src": im["src"], "thumb": im["src"], "page_url": s["url"],
                         "title": im.get("caption") or im.get("alt") or s["title"], "credit": s["domain"],
                         "origin": "source", "source_id": s["id"]})
            if s.get("og_image") and s["relevance"] >= 6:
                from_sources.append({"src": s["og_image"], "thumb": s["og_image"], "page_url": s["url"], "title": s["title"],
                     "credit": s["domain"], "origin": "source", "source_id": s["id"]})
        # mix: images from the sources first (up to ~60%), then image-search results, then the rest
        head = max(1, (limit * 3 + 4) // 5)
        for im in from_sources[:head]:
            add(im)
        for im in searched:
            if len(out) >= limit:
                break
            add(im)
        for im in from_sources[head:]:
            add(im)
        return out[:limit]

    async def choose_images(self, candidates: List[dict]) -> List[dict]:
        """Let the AI keep only pictures that really show the topic. Models that can see images look at
        them; others judge from captions and sources. On any failure the candidates are kept as they are."""
        if len(candidates) < 2:
            return candidates
        from .llm.jsonutil import extract_json
        pixels = bool(getattr(self.llm, "supports_vision", False))
        sys_p, text = prompts.judge_images(self.query, self.plan.get("intent", ""), candidates, pixels)
        user = self.llm.vision_content(text, [c["src"] for c in candidates]) if pixels else text
        try:
            async with self._sem_llm:
                raw = await self.llm.complete(sys_p + "\nRespond with ONE valid JSON object and nothing else.",
                                              user, max_tokens=300)
            keep = [int(i) for i in (extract_json(raw) or {}).get("keep", []) if str(i).isdigit()]
        except Exception:
            if not pixels:
                return candidates
            try:   # an image the provider couldn't download fails the whole request: retry from captions
                sys_p, text = prompts.judge_images(self.query, self.plan.get("intent", ""), candidates, False)
                async with self._sem_llm:
                    raw = await self.llm.complete(sys_p + "\nRespond with ONE valid JSON object and nothing else.",
                                                  text, max_tokens=300)
                keep = [int(i) for i in (extract_json(raw) or {}).get("keep", []) if str(i).isdigit()]
            except Exception:
                return candidates
        chosen = [candidates[i] for i in dict.fromkeys(keep) if 0 <= i < len(candidates)]
        return chosen

    # outcomes
    async def show_results(self, images: List[dict]) -> dict:
        await self.step("rank", "Ranking results")
        ranked = sorted([s for s in self.assessed() if s["relevance"] >= 3], key=self.score, reverse=True)
        rest = [self.sources[u] for u in self.order
                if self.sources[u].get("relevance") is None or self.sources[u]["relevance"] < 3]
        rest = [s for s in rest if s.get("status") != "error" and not s.get("out_of_range")][:12]
        best = [s["id"] for s in self.strong_matches()]
        items = [self.pub(s) for s in ranked + rest]
        await self.emit({"type": "outcome", "outcome": "results"})
        await self.emit({"type": "results", "items": items, "best": best, "images": images})
        await self.step("rank", "Ranking results", "done",
                        f"{len(best)} page(s) answer this directly" if best else f"{len(ranked)} relevant pages")
        return {"outcome": "results", "results": {"items": items, "best": best, "images": images}}

    async def write_article(self, images: List[dict]) -> dict:
        chosen = sorted(self.useful_sources(), key=self.score, reverse=True)[: int(self.r["max_article_sources"])]
        missing = [s for s in chosen if not s.get("excerpt")]   # sources carried over from an earlier search
        if missing:
            await asyncio.gather(*(self.reopen(s) for s in missing))
        for n, s in enumerate(chosen, 1):
            s["n"] = n
        art_sources = [self.pub(s) for s in chosen]
        related = [q["query"] for q in self.plan.get("related_queries", [])][:6]
        await self.step("write", "Writing the article", "running", f"Combining {len(chosen)} sources")
        await self.emit({"type": "outcome", "outcome": "article"})
        await self.emit({"type": "article_start", "sources": art_sources, "images": images, "related": related})
        md = ""
        intent = self.plan["intent"] + (f" (only information from {self.dates[0]} to {self.dates[1]})" if self.dates else "")
        async for piece in self.llm.stream(*prompts.article(self.query, intent, self.plan.get("answer_type", ""),
                                                            chosen, self.lang), max_tokens=int(self.r.get("article_max_tokens", 4096))):
            md += piece
            await self.emit({"type": "token", "text": piece})
        m = re.search(r"^#\s+(.+)$", re.sub(r"<think>.*?</think>", "", md, flags=re.S), re.M)
        await self.step("write", "Wrote the article", "done", f"{len(md.split())} words from {len(chosen)} sources")
        inter = None
        if self.extras:
            from .interactive import check
            inter = await check(self.llm, self.query, md)
            await self.emit({"type": "interactive", **inter})
        return {"outcome": "article", "article": md, "article_sources": art_sources, "related": related,
                "title": m.group(1).strip() if m else self.query, "interactive": inter}

    async def suggest(self) -> dict:
        await self.step("suggest", "Nothing reliable found - finding better searches")
        partial = [f"{s['title']} ({s['domain']}): {s.get('summary', '')}" for s in self.assessed() if s["relevance"] >= 2]
        message, items = "", []
        try:
            d = await complete_json(self.llm, *prompts.suggest(self.query, self.plan.get("intent", ""), self.tried, partial,
                                                               self.lang), max_tokens=900)
            message = str(d.get("message") or "")
            for x in d.get("suggestions") or []:
                if isinstance(x, dict) and x.get("query"):
                    items.append({"query": str(x["query"]), "why": str(x.get("why", ""))})
                elif isinstance(x, str):
                    items.append({"query": x, "why": ""})
        except Exception:
            items = [{"query": q["query"], "why": q.get("angle", "")} for q in self.plan.get("related_queries", [])]
        if not message:
            message = "None of the pages we read contained information that answers this reliably."
        partial_sources = [self.pub(s) for s in sorted(self.assessed(), key=self.score, reverse=True) if s["relevance"] >= 2][:5]
        payload = {"message": message, "items": items[:6], "tried": self.tried, "sources": partial_sources}
        await self.emit({"type": "outcome", "outcome": "suggestions"})
        await self.emit({"type": "suggestions", **payload})
        await self.step("suggest", "Suggested better searches", "done", f"{len(items)} suggestions")
        return {"outcome": "suggestions", "suggestions": payload}
