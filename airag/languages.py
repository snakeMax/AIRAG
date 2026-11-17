"""Languages AIRAG knows about.

ui=True  -> the interface has a translation in web/i18n/<code>.json
All languages can be used for answers (any modern model handles them).
To add a UI translation: copy web/i18n/en.json to <code>.json, translate the
values, and set ui=True here. Missing keys fall back to English.
"""
from __future__ import annotations

from typing import Dict, List, Optional

#            code     English name             native name            ui     DuckDuckGo region
LANGUAGES = [
    ("en",    "English",                "English",             True,  "us-en"),
    ("nb",    "Norwegian (Bokmål)",     "Norsk (bokmål)",      True,  "no-no"),
    ("sv",    "Swedish",                "Svenska",             True,  "se-sv"),
    ("da",    "Danish",                 "Dansk",               True,  "dk-da"),
    ("fi",    "Finnish",                "Suomi",               False, "fi-fi"),
    ("de",    "German",                 "Deutsch",             True,  "de-de"),
    ("fr",    "French",                 "Français",            True,  "fr-fr"),
    ("es",    "Spanish",                "Español",             True,  "es-es"),
    ("it",    "Italian",                "Italiano",            False,  "it-it"),
    ("pt",    "Portuguese",             "Português",           False,  "pt-pt"),
    ("nl",    "Dutch",                  "Nederlands",          False,  "nl-nl"),
    ("pl",    "Polish",                 "Polski",              False,  "pl-pl"),
    ("cs",    "Czech",                  "Čeština",             False, "cz-cs"),
    ("uk",    "Ukrainian",              "Українська",          False, "ua-uk"),
    ("ru",    "Russian",                "Русский",             False, "ru-ru"),
    ("tr",    "Turkish",                "Türkçe",              False, "tr-tr"),
    ("ja",    "Japanese",               "日本語",               True,  "jp-jp"),
    ("ko",    "Korean",                 "한국어",               False, "kr-kr"),
    ("zh",    "Chinese (Simplified)",   "简体中文",             True,  "cn-zh"),
    ("hi",    "Hindi",                  "हिन्दी",                False, "in-en"),
    ("id",    "Indonesian",             "Bahasa Indonesia",    False, "id-en"),
]

BY_CODE: Dict[str, tuple] = {l[0]: l for l in LANGUAGES}
ALIASES = {"no": "nb", "nn": "nb", "zh-cn": "zh", "zh-hans": "zh", "pt-br": "pt"}


def normalize(code: Optional[str]) -> Optional[str]:
    if not code:
        return None
    c = code.strip().lower().replace("_", "-")
    if c in ALIASES:
        return ALIASES[c]
    if c in BY_CODE:
        return c
    base = c.split("-")[0]
    base = ALIASES.get(base, base)
    return base if base in BY_CODE else None


def name(code: Optional[str]) -> str:
    c = normalize(code)
    return BY_CODE[c][1] if c else "English"


def region(code: Optional[str]) -> str:
    c = normalize(code)
    return BY_CODE[c][4] if c else "us-en"


def public_list() -> List[dict]:
    return [{"code": c, "name": n, "native": nat, "ui": ui} for c, n, nat, ui, _ in LANGUAGES]


def answer_language(settings: dict, ui_lang: Optional[str]) -> str:
    """Instruction text describing which language the AI should write in."""
    choice = str(settings.get("app", {}).get("answer_language") or "auto")
    if choice == "auto":
        return "the same language as the reader's search query"
    if choice == "ui":
        return name(ui_lang or "en")
    return name(choice)
