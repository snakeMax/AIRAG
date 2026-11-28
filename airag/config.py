"""Settings: JSON on disk + defaults built from provider/backend schemas.

Every provider / search backend declares its own `fields`; the UI renders the
settings form from that schema, so adding a plugin automatically adds its
settings. Secrets are masked when sent to the browser.
"""
from __future__ import annotations

import json
import os
import threading
from contextvars import ContextVar
from copy import deepcopy
from typing import Any, Iterator, List, Tuple

from . import paths
from .paths import SETTINGS_PATH

MASK = "••••"

DEFAULT_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")

SECTIONS = ("app", "llm", "search", "fetch", "research", "library", "prompts", "defaults", "usage", "audio", "speech", "buttons", "agent_tools", "effort")

GENERAL_SCHEMA: dict = {
    "app": [
        {"key": "ui_mode", "label": "Window mode", "type": "select", "default": "desktop",
         "options": [{"value": "desktop", "label": "Desktop window"}, {"value": "browser", "label": "Browser tab + tray icon"}]},
        {"key": "language", "label": "Interface language", "type": "hidden", "default": "auto"},
        {"key": "answer_language", "label": "Answer language", "type": "hidden", "default": "auto"},
        {"key": "check_updates", "label": "Check for updates when AIRAG starts", "type": "bool", "default": True},
        {"key": "guarded_execution", "label": "Guarded execution", "type": "bool", "default": True,
         "help": "Protects running tasks: settings you change while a task runs apply when it has finished (small ones, like how many results to read, from its next step), and clearing caches or history waits until running tasks finish or are cancelled."},
        {"key": "history_limit", "label": "Searches kept in history", "type": "number", "default": 300, "min": 10, "max": 5000, "step": 10,
         "help": "Older searches are deleted automatically to save space."},
        {"key": "port", "label": "Preferred port", "type": "number", "default": 8765, "min": 0, "max": 65535, "step": 1,
         "help": "If it's busy a free port is picked automatically. 0 = always pick a free one."},
        {"key": "setup_done", "label": "", "type": "hidden", "default": False},
        {"key": "disclaimer_dismissed", "label": "", "type": "hidden", "default": False},
        {"key": "include_library", "label": "", "type": "hidden", "default": False},
        {"key": "resource_graphs", "label": "Live resource graphs", "type": "bool", "default": False,
         "help": "Shows processor, memory and AI tokens per minute in the activity bar while AIRAG is open. Phones show battery and temperature instead of the processor."},
        {"key": "resource_style", "label": "Graph colours", "type": "select", "default": "accent",
         "options": ["accent", "plain"], "help": "Accent: your accent colour. Plain: grey, following light or dark mode."},
        {"key": "appearance", "label": "", "type": "hidden",
         "default": {"theme": "system", "palette": "zinc", "accent": "graphite",
                     "uiFont": "system", "articleFont": "serif", "textSize": 2}},
        {"key": "theme_hint", "label": "", "type": "hidden", "default": "light"},
        {"key": "pclink_enabled", "label": "", "type": "hidden", "default": False},
        {"key": "pclink_port", "label": "", "type": "hidden", "default": 0},
        {"key": "pclink_code", "label": "", "type": "hidden", "default": ""},
        {"key": "pclink_allow_internet", "label": "", "type": "hidden", "default": False},
    ],
    # what new searches start with (each can still be changed for one search on the home page)
    "defaults": [
        {"key": "mode", "label": "Search mode", "type": "select", "default": "auto", "options": ["auto", "article", "results"]},
        {"key": "library", "label": "Include My library", "type": "bool", "default": False,
         "help": "Tick My library on the home page by default."},
        {"key": "extras", "label": "Pictures and interactive explainer", "type": "bool", "default": True,
         "help": "Look for pictures and check whether an interactive explainer fits. Turn off to use fewer AI tokens."},
        {"key": "dates", "label": "Time range", "type": "select", "default": "any", "options": ["any", "week", "month", "year"]},
        {"key": "translate_to", "label": "Translate into", "type": "hidden", "default": ""},
        {"key": "save_rich", "label": "Save articles with pictures and the explainer", "type": "bool", "default": False},
        {"key": "citation_style", "label": "Citation style", "type": "select", "default": "apa",
         "options": ["apa", "mla", "bibtex"], "help": "Used by Cite and Copy with source."},
        {"key": "pinned_view", "label": "Open pinned sources as", "type": "select", "default": "fetched",
         "options": ["fetched", "generated"],
         "help": "Fetched: the saved copy of the page. Generated: a short AI-written version focused on why you pinned it."},
        {"key": "speech_autosearch", "label": "Search as soon as you stop speaking", "type": "bool", "default": True,
         "help": "After speaking into the microphone, the search starts by itself. Off: check or edit the text first."},
    ],
    # which tool buttons are shown on articles, results and sources (Settings -> Appearance); all on by default
    "buttons": [
        {"key": k, "label": lab, "type": "bool", "default": True} for k, lab in (
            ("summarize", "Summarize"), ("interactive", "Interactive explainer"), ("results", "Search results"),
            ("more_sources", "Locate more sources"), ("save", "Save"), ("copy", "Copy as Markdown"),
            ("translate", "Translate with AI"), ("listen", "Listen (read aloud)"), ("pin", "Pin article"),
            ("export", "Export web page"), ("summary_file", "Download summary"), ("regenerate", "Regenerate article"), ("source_summarize", "Summarize (on sources)"),
            ("source_save", "Save page (on sources)"), ("source_pin", "Pin source (on sources)"),
            ("to_notes", "Add to notes"), ("source_to_notes", "Add to notes (on sources)"))
    ],
    # sound effects (Settings -> Appearance -> Customize audio); edited by its own panel
    "audio": [
        {"key": "enabled", "label": "Sound effects", "type": "hidden", "default": True},
        {"key": "master", "label": "Master volume", "type": "hidden", "default": 80},
        {"key": "sounds", "label": "", "type": "hidden", "default": {
            n: {"vol": 70, "file": ""} for n in ("mic_start", "mic_stop", "search_done", "explainer_done", "task_failed")}},
    ],
    # read aloud (text to speech)
    "speech": [
        {"key": "voice", "label": "Voice", "type": "hidden", "default": "female"},
        {"key": "rate", "label": "Speed", "type": "hidden", "default": 1.0},
    ],
    # which tools each agent type may use (Settings -> Tools; saved immediately by /api/agent-tools)
    "agent_tools": [
        {"key": "picker", "label": "", "type": "hidden", "default": "autonomous"},
        {"key": "sets", "label": "", "type": "hidden", "default": {}},
    ],
    # quality vs. token saving, one mode per agent type (Settings -> Usage; saved immediately)
    "effort": [
        {"key": "standard", "label": "", "type": "hidden", "default": "medium"},
        {"key": "autonomous", "label": "", "type": "hidden", "default": "medium"},
        {"key": "subagents", "label": "", "type": "hidden", "default": "medium"},
    ],
    # token and cost tracking (Settings -> Usage)
    # Notes Mode: where the Notes folder is (empty = Documents/AIRAG Notes, or D:\\AIRAG Notes on a PC with a D: drive)
    "notes": [
        {"key": "root", "label": "", "type": "hidden", "default": ""},
        {"key": "main", "label": "", "type": "hidden", "default": ""},   # id of the main notes vault
    ],
    # groundwork for 0.5.0 agents (airag.agents.Limits reads these; not shown in Settings yet)
    "agents": [
        {"key": "max_steps", "label": "", "type": "hidden", "default": 30},
        {"key": "max_tool_calls", "label": "", "type": "hidden", "default": 25},
        {"key": "retries", "label": "", "type": "hidden", "default": 2},
        {"key": "tool_timeout", "label": "", "type": "hidden", "default": 30},
        {"key": "cost_cap", "label": "", "type": "hidden", "default": 1.0},
        {"key": "token_limit", "label": "", "type": "hidden", "default": 0},
        {"key": "subagents", "label": "", "type": "hidden", "default": 1},
        {"key": "subagent_token_share", "label": "", "type": "hidden", "default": 0.7},
    ],
    # groundwork for the enterprise edition (airag.editions); unused by the personal editions
    "enterprise": [
        {"key": "server_url", "label": "", "type": "hidden", "default": ""},
        {"key": "organization", "label": "", "type": "hidden", "default": ""},
    ],
    "usage": [
        {"key": "monthly_budget", "label": "Monthly budget ($)", "type": "number", "default": 5, "min": 0, "max": 10000, "step": 1,
         "help": "Shown as a bar in Settings -> Usage. 0 = no budget."},
        {"key": "tell_model", "label": "Tell the AI when the budget is nearly used", "type": "bool", "default": True,
         "help": "When 70% is used, the AI is asked to search less and write shorter answers."},
        {"key": "stop_at_budget", "label": "Stop new AI work when the budget is used up", "type": "bool", "default": False,
         "help": "Searches, follow-ups, rewrites, explainers, summaries, translations and image analysis. Work that's already running finishes."},
    ],
    "library": [
        {"key": "folders", "label": "Folders", "type": "hidden", "default": []},
        {"key": "personal_folder", "label": "", "type": "hidden", "default": ""},
        {"key": "web_too", "label": "Also search the web when 'My library' is ticked", "type": "bool", "default": True,
         "help": "Turn off to answer only from your own files."},
        {"key": "offline", "label": "Offline mode", "type": "hidden", "default": False},
        {"key": "offline_writer", "label": "", "type": "hidden", "default": "current"},
        {"key": "offline_provider", "label": "", "type": "hidden", "default": ""},
        {"key": "offline_model", "label": "", "type": "hidden", "default": ""},
        {"key": "reopen_to_history", "label": "Reopened saved articles go back in History", "type": "bool", "default": True,
         "help": "So follow-ups and the other toolbar tools work on them."},
        {"key": "extensions", "label": "File types", "type": "text",
         "default": ".md, .markdown, .txt, .text, .rst, .org, .tex, .log, .pdf, .docx, .odt, .rtf, .pptx, .odp, .html, .htm, .csv, .tsv, .json, .xlsx, .ods, .db, .sqlite",
         "help": "Comma separated. Readable: text and Markdown, PDF, Word (.docx), PowerPoint (.pptx), Excel (.xlsx), OpenDocument, RTF, web pages, CSV, JSON and SQLite databases (read-only)."},
        {"key": "max_file_mb", "label": "Skip files larger than (MB)", "type": "number", "default": 25, "min": 1, "max": 500, "step": 1},
        {"key": "max_results", "label": "Library files read per search", "type": "number", "default": 6, "min": 1, "max": 30, "step": 1},
        {"key": "min_relevance", "label": "Minimum relevance to use a library file (1-10)", "type": "number", "default": 4, "min": 1, "max": 10, "step": 1,
         "help": "Library files the AI rates below this for the question are left out and not listed."},
        {"key": "trust", "label": "Default reliability of your own files (0-10)", "type": "number", "default": 6, "min": 0, "max": 10, "step": 1,
         "help": "The AI still judges each file. Personal notes are useful but not independently verified."},
    ],
    "prompts": [
        {"key": "style", "label": "Writing style", "type": "select", "default": "balanced",
         "options": ["balanced", "concise", "detailed", "academic", "simple"]},
        {"key": "length", "label": "Article length", "type": "select", "default": "auto",
         "options": ["auto", "short", "medium", "long"]},
        {"key": "explainer_level", "label": "Interactive explainer detail", "type": "select", "default": "medium",
         "options": ["simple", "medium", "detailed"],
         "help": "Simple uses the fewest tokens; detailed makes richer simulations and games but costs more."},
        {"key": "custom_instructions", "label": "Your instructions", "type": "textarea", "default": "",
         "help": "Added to the article, summary and explainer prompts. E.g. 'Always use metric units', 'Prefer peer-reviewed sources', 'Explain like I'm a nurse'."},
        {"key": "planner_instructions", "label": "Search instructions", "type": "textarea", "default": "",
         "help": "Added to the search planner. E.g. 'Include Norwegian sources', 'Avoid Reddit'."},
        {"key": "article_prompt", "label": "Article prompt (advanced)", "type": "prompt", "default": "",
         "help": "Replaces the main article instructions. Leave empty to use the default. Safety rules and the answer language are always added."},
    ],
    "llm": [
        {"key": "temperature", "label": "Temperature", "type": "number", "default": 0.3,
         "min": 0, "max": 1.5, "step": 0.05, "help": "Lower is more factual and consistent."},
        # {provider: {task: model}}; empty = every task uses the provider's main model (Sonnet 5.5 for Claude).
        {"key": "task_models", "label": "", "type": "hidden", "default": {}},
    ],
    "search": [
        {"key": "use_wikis", "label": "Also search wikis", "type": "bool", "default": True,
         "help": "Searches Wikipedia (in your answer language) and any wikis you add, next to the search engine."},
        {"key": "wiki_results", "label": "Wiki pages per search", "type": "number", "default": 2, "min": 1, "max": 6, "step": 1},
        {"key": "wikis", "label": "", "type": "hidden", "default": [
            {"name": "Wikipedia", "api": "wikipedia", "about": "General encyclopedia: overviews, history, science, people, places.",
             "enabled": True, "trust": 7}]},
        {"key": "region", "label": "Region", "type": "text", "default": "auto",
         "help": "auto = based on your answer language. Or a code like us-en, uk-en, no-no, de-de, wt-wt (worldwide)."},
        {"key": "safesearch", "label": "Safe search", "type": "select", "default": "moderate",
         "options": ["off", "moderate", "strict"]},
    ],
    "fetch": [
        {"key": "allow_local_network", "label": "Read pages on my local network", "type": "bool", "default": False,
         "help": "Off: links to this computer (127.0.0.1, localhost) or your local network (router, NAS, 192.168.x.x) are never read, so their contents can't reach the AI. Turn on only if you search your own intranet pages."},
        {"key": "fetcher", "label": "Page reader", "type": "select", "default": "auto",
         "options": ["auto", "http", "browser"],
         "help": "auto = fast HTTP first, headless browser for pages that need JavaScript "
                 "(browser requires the optional Playwright install)."},
        {"key": "timeout", "label": "Page timeout (s)", "type": "number", "default": 15, "min": 3, "max": 120, "step": 1},
        {"key": "max_concurrency", "label": "Pages read in parallel", "type": "number", "default": 6, "min": 1, "max": 20, "step": 1},
        {"key": "youtube", "label": "Read YouTube videos", "type": "bool", "default": True,
         "help": "Reads a video's title, description and captions (spoken text) so it can be used as a source."},
        {"key": "wikipedia_api", "label": "Read Wikipedia through its API", "type": "bool", "default": True,
         "help": "Reads Wikipedia (and other Wikimedia sites) through their official API with an honest app name, as Wikimedia asks. Off: read like any other web page (often refused)."},
        {"key": "youtube_retries", "label": "YouTube retries", "type": "number", "default": 1, "min": 0, "max": 5, "step": 1,
         "help": "How many times to try again when YouTube doesn't answer."},
        {"key": "user_agent", "label": "User agent", "type": "text", "default": DEFAULT_UA},
    ],
    "research": [
        {"key": "explainer_local_examples", "label": "Explainers: learn from code in My library", "type": "bool", "default": True,
         "help": "JavaScript in your own library files that matches the explainer can be used as a reference. Nothing is fetched from the web."},
        {"key": "explainer_web_examples", "label": "Explainers: look up code examples on the web", "type": "bool", "default": False,
         "help": "Only used when your search itself is about programming. Code from the web can hide instructions or mistakes, so it's off by default."},
        {"key": "use_pinned", "label": "Use pinned sources in searches", "type": "bool", "default": True,
         "help": "Pinned pages that match the question are read from their saved copy (no download) and can be cited."},
        {"key": "max_rounds", "label": "Max search rounds", "type": "number", "default": 3, "min": 1, "max": 6, "step": 1,
         "help": "Round 1 = direct searches, round 2 = related/indirect searches, 3+ = gap-filling searches."},
        {"key": "results_per_query", "label": "Results per query", "type": "number", "default": 8, "min": 3, "max": 20, "step": 1},
        {"key": "sources_per_round", "label": "Pages read per round", "type": "number", "default": 8, "min": 1, "max": 20, "step": 1,
         "help": "Pages that can't be opened (blocked sites, bot checks) don't count: others are read in their place."},
        {"key": "max_sources_total", "label": "Max pages read in total", "type": "number", "default": 20, "min": 2, "max": 60, "step": 1},
        {"key": "llm_concurrency", "label": "Parallel AI calls", "type": "number", "default": 3, "min": 1, "max": 10, "step": 1,
         "help": "Use 1 for small local models."},
        {"key": "passage_chars", "label": "Text per page sent to AI (chars)", "type": "number", "default": 3500, "min": 800, "max": 20000, "step": 100},
        {"key": "long_page_pick", "label": "Let the AI pick sections of long pages", "type": "bool", "default": True,
         "help": "Long pages are read section by section. When a long page's sections barely use the search's key words, a small AI call picks the sections to read from its headings (a few hundred tokens)."},
        {"key": "direct_relevance", "label": "Direct-hit relevance threshold", "type": "number", "default": 8, "min": 1, "max": 10, "step": 1,
         "help": "A page this relevant AND comprehensive makes AIRAG show ranked results instead of writing an article."},
        {"key": "direct_coverage", "label": "Direct-hit coverage threshold", "type": "number", "default": 7, "min": 1, "max": 10, "step": 1},
        {"key": "min_findings", "label": "Min findings to write an article", "type": "number", "default": 2, "min": 1, "max": 20, "step": 1},
        {"key": "enough_findings", "label": "Stop searching after N findings", "type": "number", "default": 10, "min": 2, "max": 60, "step": 1},
        {"key": "article_max_tokens", "label": "Max article length (tokens)", "type": "number", "default": 8192, "min": 512, "max": 32000, "step": 256,
         "help": "Upper limit for the answer. Reasoning models count their thinking here too, so keep it generous."},
        {"key": "max_article_sources", "label": "Max sources per article", "type": "number", "default": 12, "min": 2, "max": 30, "step": 1},
        {"key": "images", "label": "Find images", "type": "hidden", "default": True},
        {"key": "interactive_check", "label": "Offer interactive explainers for articles", "type": "hidden", "default": True,
         "help": "After writing an article, the AI checks whether a small simulation would help explain it (one extra short AI call)."},
        {"key": "max_images", "label": "Max images", "type": "number", "default": 6, "min": 0, "max": 20, "step": 1},
        {"key": "skip_domains", "label": "Blocked sites", "type": "text",
         "default": "tiktok.com, instagram.com, facebook.com, x.com, twitter.com, pinterest.com",
         "help": "Comma separated. Never read. A site name covers all its subdomains; add a path (site.com/forum) "
                 "to block only that directory and everything below it."},
        {"key": "favourite_sites", "label": "Favourite sites", "type": "text", "default": "",
         "help": "Comma separated, same rules as blocked sites. Pages from these start with a higher trust score."},
    ],
}

_lock = threading.Lock()


def field_defaults(fields: List[dict]) -> dict:
    return {f["key"]: deepcopy(f.get("default", "")) for f in fields}


def defaults() -> dict:
    d = _base_defaults()
    if paths.ANDROID:  # lighter defaults for phones: less battery, data and storage
        d["llm"]["provider"] = "anthropic"
        d["search"]["image_backend"] = "none"
        d["fetch"]["max_concurrency"] = 3
        d["fetch"]["fetcher"] = "http"
        d["research"].update({"sources_per_round": 5, "max_sources_total": 14, "llm_concurrency": 2,
                              "max_rounds": 3, "max_images": 4})
        d["app"]["history_limit"] = 100
    return d


def _base_defaults() -> dict:
    from .llm import PROVIDERS
    from .search import BACKENDS
    return {
        "app": field_defaults(GENERAL_SCHEMA["app"]),
        "prompts": field_defaults(GENERAL_SCHEMA["prompts"]),
        "library": field_defaults(GENERAL_SCHEMA["library"]),
        "llm": {"provider": "ollama", **field_defaults(GENERAL_SCHEMA["llm"]),
                "providers": {n: field_defaults(c.fields) for n, c in PROVIDERS.items()}},
        "search": {"backend": "duckduckgo", "image_backend": "duckduckgo",
                   **field_defaults(GENERAL_SCHEMA["search"]),
                   "backends": {n: field_defaults(c.fields) for n, c in BACKENDS.items()}},
        "fetch": field_defaults(GENERAL_SCHEMA["fetch"]),
        "research": field_defaults(GENERAL_SCHEMA["research"]),
        "defaults": field_defaults(GENERAL_SCHEMA["defaults"]),
        "usage": field_defaults(GENERAL_SCHEMA["usage"]),
        "audio": field_defaults(GENERAL_SCHEMA["audio"]),
        "speech": field_defaults(GENERAL_SCHEMA["speech"]),
        "buttons": field_defaults(GENERAL_SCHEMA["buttons"]),
        "agent_tools": field_defaults(GENERAL_SCHEMA["agent_tools"]),
        "effort": field_defaults(GENERAL_SCHEMA["effort"]),
        "notes": field_defaults(GENERAL_SCHEMA["notes"]),
        "agents": field_defaults(GENERAL_SCHEMA["agents"]),
        "enterprise": field_defaults(GENERAL_SCHEMA["enterprise"]),
    }


def deep_merge(base: dict, over: dict) -> dict:
    out = deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = deepcopy(v)
    return out


def _secret_fields() -> Iterator[Tuple[List[str], dict]]:
    from .llm import PROVIDERS
    from .search import BACKENDS
    for n, c in PROVIDERS.items():
        for f in c.fields:
            if f.get("type") == "secret":
                yield ["llm", "providers", n, f["key"]], f
    for n, c in BACKENDS.items():
        for f in c.fields:
            if f.get("type") == "secret":
                yield ["search", "backends", n, f["key"]], f


def _get(d: dict, path: List[str]) -> Any:
    for p in path:
        if not isinstance(d, dict):
            return None
        d = d.get(p)
    return d


def _set(d: dict, path: List[str], v: Any) -> None:
    for p in path[:-1]:
        d = d.setdefault(p, {})
    d[path[-1]] = v


def _coerce(s: dict) -> dict:
    for section in SECTIONS:
        for f in GENERAL_SCHEMA[section]:
            k, v = f["key"], s[section].get(f["key"])
            try:
                if f["type"] == "number":
                    v = float(v)
                    s[section][k] = int(v) if float(f.get("step", 1)).is_integer() and v.is_integer() else v
                elif f["type"] == "bool":
                    s[section][k] = v if isinstance(v, bool) else str(v).lower() in ("1", "true", "yes", "on")
            except (TypeError, ValueError):
                s[section][k] = f.get("default")
    return s


def _backup_path():
    return SETTINGS_PATH.with_name(SETTINGS_PATH.name + ".bak")


def load_raw() -> dict:
    """The saved settings. If the file is damaged (e.g. a crash while an older version wrote it), the damaged
    file is put aside and the last good copy is used, never the defaults (which would lose keys and folders)."""
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
        raise ValueError("not an object")
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        pass
    import logging
    import time as _t
    log = logging.getLogger("airag")
    try:
        damaged = SETTINGS_PATH.with_name(f"settings.damaged-{_t.strftime('%Y%m%d-%H%M%S')}.json")
        if SETTINGS_PATH.exists() and not any(SETTINGS_PATH.parent.glob("settings.damaged-*.json")):
            SETTINGS_PATH.replace(damaged)
            log.error("settings file was damaged; kept it as %s", damaged.name)
    except OSError:
        pass
    try:
        data = json.loads(_backup_path().read_text(encoding="utf-8"))
        if isinstance(data, dict):
            log.warning("using the last good copy of the settings")
            from .paths import atomic_write_text
            atomic_write_text(SETTINGS_PATH, json.dumps(data, indent=2, ensure_ascii=False))
            return data
    except (OSError, ValueError):
        pass
    return {}


# ---------------------------------------------------------------- settings while a task runs (guarded execution)
# Each background task works with the settings it started with, so a change in Settings can't corrupt a search,
# switch its AI model halfway or stop it. Changes reach the task in two ways:
#  - LIVE keys (how much to read, how many results...) are picked up at the task's next step (live_update);
#  - everything else applies to the next task.
# Without guarded execution, tasks read the settings file directly (the behaviour before 0.4.1).
_JOB: "ContextVar[dict | None]" = ContextVar("airag_job_settings", default=None)

LIVE_KEYS = (
    ("research", "results_per_query"), ("research", "sources_per_round"), ("research", "max_sources_total"),
    ("research", "max_rounds"), ("research", "max_images"), ("research", "images"), ("research", "max_article_sources"),
    ("research", "skip_domains"), ("research", "favourite_sites"), ("research", "enough_findings"),
    ("fetch", "timeout"), ("fetch", "youtube"), ("fetch", "wikipedia_api"), ("library", "max_results"), ("library", "min_relevance"),
)
# settings that only change what you see or hear, never how a running task works
UI_ONLY = {"audio", "speech", "buttons", "defaults"}
UI_ONLY_KEYS = {("app", "appearance"), ("app", "resource_graphs"), ("app", "resource_style"), ("app", "theme_hint"), ("app", "language"), ("app", "disclaimer_dismissed"),
                ("app", "setup_done"), ("app", "check_updates"), ("app", "guarded_execution"), ("app", "ui_mode")}


def guarded() -> bool:
    try:
        return bool(deep_merge(defaults(), load_raw())["app"].get("guarded_execution", True))
    except Exception:
        return True


def begin_job():
    """Called when a background task starts: it gets its own copy of the settings (guarded execution).
    Returns a token for end_job, or None when tasks read the settings live."""
    if not guarded():
        return None
    return _JOB.set(load())


def end_job(token) -> None:
    if token is not None:
        _JOB.reset(token)


def in_job() -> bool:
    return _JOB.get() is not None


def live_update(current: dict) -> dict:
    """At a task's next step: the LIVE keys from the settings file, everything else unchanged. Values that don't
    fit their type are ignored, so a half-typed setting can't break the task."""
    try:
        fresh = _coerce(deep_merge(defaults(), load_raw()))
    except Exception:
        return current
    out = deepcopy(current)
    for sec, key in LIVE_KEYS:
        if sec in fresh and key in fresh[sec] and sec in out:
            old = out[sec].get(key)
            new = fresh[sec][key]
            if old is None or type(new) is type(old) or (isinstance(old, (int, float)) and isinstance(new, (int, float))):
                out[sec][key] = new
    snap = _JOB.get()
    if snap is not None:                  # the rest of the task (helpers that load settings) sees them too
        for sec, key in LIVE_KEYS:
            if sec in out and key in out[sec] and sec in snap:
                snap[sec][key] = out[sec][key]
    return out


def changed_for_running(before: dict, after: dict) -> List[str]:
    """Sections whose changes a running task won't see until it has finished (for the "applies later" note)."""
    live = set(LIVE_KEYS)
    out = []
    for sec in SECTIONS:
        if sec in UI_ONLY:
            continue
        a, b = before.get(sec, {}), after.get(sec, {})
        if not isinstance(a, dict) or not isinstance(b, dict):
            continue
        for key in set(a) | set(b):
            if (sec, key) in live or (sec, key) in UI_ONLY_KEYS:
                continue
            if a.get(key) != b.get(key):
                out.append(sec)
                break
    return out


def load(with_env: bool = True) -> dict:
    snap = _JOB.get()
    if snap is not None:                  # inside a running task: the task's own copy
        return deepcopy(snap)
    raw = load_raw()
    if "defaults" not in raw and raw.get("app", {}).get("include_library"):
        raw["defaults"] = {"library": True}   # 0.2 kept the My library tickbox in "app"
    old_skip = "youtube.com, tiktok.com, instagram.com, facebook.com, x.com, twitter.com, pinterest.com"
    if raw.get("research", {}).get("skip_domains") == old_skip:   # YouTube can be read now (0.4)
        raw["research"]["skip_domains"] = old_skip.replace("youtube.com, ", "")
    if raw.get("research", {}).get("article_max_tokens") == 4096:
        raw["research"]["article_max_tokens"] = 8192   # old default, too low for reasoning models
    res = raw.get("research", {})
    old = (4, 10, 2) if paths.ANDROID else (6, 16, 3)        # 0.4.1: read a bit more (blocked pages are replaced)
    if (res.get("sources_per_round"), res.get("max_sources_total"), res.get("max_rounds")) == old:
        res.update({"sources_per_round": 5, "max_sources_total": 14, "max_rounds": 3} if paths.ANDROID
                   else {"sources_per_round": 8, "max_sources_total": 20})
    lib = raw.get("library", {})
    if lib.get("extensions") == ".md, .markdown, .txt, .text, .rst, .org, .tex, .pdf, .docx, .odt, .html, .htm, .csv, .json, .log":
        lib["extensions"] = ".md, .markdown, .txt, .text, .rst, .org, .tex, .log, .pdf, .docx, .odt, .rtf, .pptx, .odp, .html, .htm, .csv, .tsv, .json, .xlsx, .ods, .db, .sqlite"    # 0.4.1: more file types; only when the list was never changed
    s = _coerce(deep_merge(defaults(), raw))
    if with_env:
        for path, f in _secret_fields():
            if not _get(s, path) and f.get("env") and os.environ.get(f["env"]):
                _set(s, path, os.environ[f["env"]])
    return s


def masked(s: dict) -> dict:
    s = deepcopy(s)
    for path, _ in _secret_fields():
        v = _get(s, path)
        if v:
            _set(s, path, MASK + (v[-4:] if len(v) > 10 else ""))
    return s


def unmask_into(new: dict, current: dict) -> dict:
    for path, _ in _secret_fields():
        v = _get(new, path)
        if isinstance(v, str) and v.startswith(MASK):
            _set(new, path, _get(current, path) or "")
    return new


def save(incoming: dict) -> dict:
    with _lock:
        current = deep_merge(defaults(), load_raw())
        new = unmask_into(deep_merge(current, incoming), current)
        tm = (incoming.get("llm") or {}).get("task_models") if isinstance(incoming.get("llm"), dict) else None
        if tm is not None:         # replaced, not merged, so "use the main model" can remove an entry
            from .llm.tasks import clean_table
            new["llm"]["task_models"] = clean_table(tm)
        paths.ensure_dirs()
        try:                       # keep the previous good copy, in case something goes wrong later
            if SETTINGS_PATH.exists():
                json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
                paths.atomic_write_text(_backup_path(), SETTINGS_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
        paths.atomic_write_text(SETTINGS_PATH, json.dumps(new, indent=2, ensure_ascii=False))
    return load()


def with_overrides(settings: dict, llm_provider: str, provider_cfg: dict) -> dict:
    """Settings with an unsaved provider config from the form (for Test / Load models)."""
    s = deepcopy(settings)
    s["llm"]["provider"] = llm_provider
    cur = s["llm"]["providers"].get(llm_provider, {})
    merged = deep_merge(cur, provider_cfg or {})
    for k, v in list(merged.items()):
        if isinstance(v, str) and v.startswith(MASK):
            merged[k] = cur.get(k, "")
    s["llm"]["providers"][llm_provider] = merged
    return s
