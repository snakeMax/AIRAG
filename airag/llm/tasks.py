"""Which AI model each kind of work uses ("Models per task", Settings -> AI).

Every call to get_llm() names its task. When the user picked a model for that task
(settings["llm"]["task_models"][provider][task]), that model is used for every AI call
belonging to the task; otherwise the provider's main model is used (Sonnet 5.5 by
default for Claude). Offline mode's local model always wins.

A running task keeps the model it started with: tasks take their settings copy when
they start (guarded execution), and the model is resolved from that copy.
"""
from __future__ import annotations

from typing import Dict, List, Optional

# id -> (label, hint). Registration order = order shown in Settings.
TASKS: Dict[str, Dict[str, str]] = {
    "research": {"label": "Research & writing", "hint": "Plans searches, judges pages, writes the article, Locate more sources"},
    "quick": {"label": "Quick search", "hint": "Short cited answers"},
    "followup": {"label": "Follow-ups & toolbar", "hint": "Answers, compare, timeline, fact-check, calculate, elaborate"},
    "rewrite": {"label": "Rewrite & regenerate", "hint": "Rewrites and new versions of an article"},
    "summary": {"label": "Summaries", "hint": "Summaries and downloaded summaries"},
    "translate": {"label": "Translation", "hint": "Translating articles"},
    "tags": {"label": "Tags", "hint": "Suggest tags (cheap models work well)"},
    "explainer": {"label": "Explainers", "hint": "Interactive explainers and charts"},
    "vision": {"label": "Image analysis", "hint": "Needs a model that can see pictures"},
    "notes": {"label": "Notes", "hint": "Organizing voice notes, and later smart search and Ask your notes"},
    "misc": {"label": "Small helpers", "hint": "Describing wikis and other short one-off jobs"},
}

# Providers whose task table is shown in Settings. The code works for any provider;
# the UI starts with Claude (user, 24 Nov 2026) and can add others later.
UI_PROVIDERS = ("anthropic",)


def task_ids() -> List[str]:
    return list(TASKS)


def model_for(settings: dict, provider: str, task: Optional[str]) -> str:
    """The model picked for `task` with `provider`, or "" (= use the provider's main model)."""
    if not task:
        return ""
    if task not in TASKS:
        raise ValueError(f"Unknown AI task '{task}'")   # a typo in a call site must fail loudly in tests
    table = (settings.get("llm", {}).get("task_models") or {}).get(provider) or {}
    value = table.get(task, "")
    return value.strip() if isinstance(value, str) else ""


def clean_table(raw) -> dict:
    """Validate a task_models value coming from the settings form: {provider: {task: model}}."""
    out: dict = {}
    if not isinstance(raw, dict):
        return out
    for prov, table in raw.items():
        if not isinstance(prov, str) or not isinstance(table, dict):
            continue
        row = {}
        for task, model in table.items():
            if task in TASKS and isinstance(model, str) and len(model) <= 200:
                m = model.strip()
                if m and all(ch.isalnum() or ch in "-._:/@" for ch in m):
                    row[task] = m
        if row:
            out[prov[:40]] = row
    return out
