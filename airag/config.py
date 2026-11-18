"""Settings: JSON on disk + defaults built from provider/backend schemas.

Every provider / search backend declares its own `fields`; the UI renders the
settings form from that schema, so adding a plugin automatically adds its
settings. Secrets are masked when sent to the browser.
"""
from __future__ import annotations

import json
import os
import threading
from copy import deepcopy
from typing import Any, Iterator, List, Tuple

from . import paths
from .paths import SETTINGS_PATH

MASK = "••••"

DEFAULT_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")

SECTIONS = ("app", "llm", "search", "fetch", "research", "library", "prompts", "defaults", "usage", "audio", "speech", "buttons")

GENERAL_SCHEMA: dict = {
    "app": [
        {"key": "ui_mode", "label": "Window mode", "type": "select", "default": "desktop",
         "options": [{"value": "desktop", "label": "Desktop window"}, {"value": "browser", "label": "Browser tab + tray icon"}]},
        {"key": "language", "label": "Interface language", "type": "hidden", "default": "auto"},
        {"key": "answer_language", "label": "Answer language", "type": "hidden", "default": "auto"},
        {"key": "check_updates", "label": "Check for updates when AIRAG starts", "type": "bool", "default": True},
        {"key": "history_limit", "label": "Searches kept in history", "type": "number", "default": 300, "min": 10, "max": 5000, "step": 10,
         "help": "Older searches are deleted automatically to save space."},
        {"key": "port", "label": "Preferred port", "type": "number", "default": 8765, "min": 0, "max": 65535, "step": 1,
         "help": "If it's busy a free port is picked automatically. 0 = always pick a free one."},
        {"key": "setup_done", "label": "", "type": "hidden", "default": False},
        {"key": "disclaimer_dismissed", "label": "", "type": "hidden", "default": False},
        {"key": "include_library", "label": "", "type": "hidden", "default": False},
        {"key": "appearance", "label": "", "type": "hidden",
         "default": {"theme": "system", "palette": "zinc", "accent": "graphite"}},
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
            ("export", "Export web page"), ("source_summarize", "Summarize (on sources)"),
            ("source_save", "Save page (on sources)"), ("source_pin", "Pin source (on sources)"))
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
    # token and cost tracking (Settings -> Usage)
    "usage": [
        {"key": "monthly_budget", "label": "Monthly budget ($)", "type": "number", "default": 5, "min": 0, "max": 10000, "step": 1,
         "help": "Shown as a bar in Settings -> Usage. 0 = no budget."},
        {"key": "tell_model", "label": "Tell the AI when the budget is nearly used", "type": "bool", "default": True,
         "help": "When 70% is used, the AI is asked to search less and write shorter answers."},
        {"key": "stop_at_budget", "label": "Stop new searches when the budget is used up", "type": "bool", "default": False},
    ],
    "library": [
        {"key": "folders", "label": "Folders", "type": "hidden", "default": []},
        {"key": "personal_folder", "label": "", "type": "hidden", "default": ""},
        {"key": "web_too", "label": "Also search the web when 'My library' is ticked", "type": "bool", "default": True,
         "help": "Turn off to answer only from your own files."},
        {"key": "extensions", "label": "File types", "type": "text",
         "default": ".md, .markdown, .txt, .text, .rst, .org, .tex, .pdf, .docx, .odt, .html, .htm, .csv, .json, .log",
         "help": "Comma separated."},
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
        {"key": "fetcher", "label": "Page reader", "type": "select", "default": "auto",
         "options": ["auto", "http", "browser"],
         "help": "auto = fast HTTP first, headless browser for pages that need JavaScript "
                 "(browser requires the optional Playwright install)."},
        {"key": "timeout", "label": "Page timeout (s)", "type": "number", "default": 15, "min": 3, "max": 120, "step": 1},
        {"key": "max_concurrency", "label": "Pages read in parallel", "type": "number", "default": 6, "min": 1, "max": 20, "step": 1},
        {"key": "youtube", "label": "Read YouTube videos", "type": "bool", "default": True,
         "help": "Reads a video's title, description and captions (spoken text) so it can be used as a source."},
        {"key": "youtube_retries", "label": "YouTube retries", "type": "number", "default": 1, "min": 0, "max": 5, "step": 1,
         "help": "How many times to try again when YouTube doesn't answer."},
        {"key": "user_agent", "label": "User agent", "type": "text", "default": DEFAULT_UA},
    ],
    "research": [
        {"key": "use_pinned", "label": "Use pinned sources in searches", "type": "bool", "default": True,
         "help": "Pinned pages that match the question are read from their saved copy (no download) and can be cited."},
        {"key": "max_rounds", "label": "Max search rounds", "type": "number", "default": 3, "min": 1, "max": 6, "step": 1,
         "help": "Round 1 = direct searches, round 2 = related/indirect searches, 3+ = gap-filling searches."},
        {"key": "results_per_query", "label": "Results per query", "type": "number", "default": 8, "min": 3, "max": 20, "step": 1},
        {"key": "sources_per_round", "label": "Pages read per round", "type": "number", "default": 6, "min": 1, "max": 20, "step": 1},
        {"key": "max_sources_total", "label": "Max pages read in total", "type": "number", "default": 16, "min": 2, "max": 60, "step": 1},
        {"key": "llm_concurrency", "label": "Parallel AI calls", "type": "number", "default": 3, "min": 1, "max": 10, "step": 1,
         "help": "Use 1 for small local models."},
        {"key": "passage_chars", "label": "Text per page sent to AI (chars)", "type": "number", "default": 3500, "min": 800, "max": 20000, "step": 100},
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
        d["research"].update({"sources_per_round": 4, "max_sources_total": 10, "llm_concurrency": 2,
                              "max_rounds": 2, "max_images": 4})
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


def load_raw() -> dict:
    try:
        return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def load(with_env: bool = True) -> dict:
    raw = load_raw()
    if "defaults" not in raw and raw.get("app", {}).get("include_library"):
        raw["defaults"] = {"library": True}   # 0.2 kept the My library tickbox in "app"
    old_skip = "youtube.com, tiktok.com, instagram.com, facebook.com, x.com, twitter.com, pinterest.com"
    if raw.get("research", {}).get("skip_domains") == old_skip:   # YouTube can be read now (0.4)
        raw["research"]["skip_domains"] = old_skip.replace("youtube.com, ", "")
    if raw.get("research", {}).get("article_max_tokens") == 4096:
        raw["research"]["article_max_tokens"] = 8192   # old default, too low for reasoning models
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
        paths.ensure_dirs()
        tmp = SETTINGS_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(new, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(SETTINGS_PATH)
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
