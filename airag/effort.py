"""Effort modes: how much an agent spends on quality vs. saving tokens.

Each agent type (standard, autonomous, sub-agents) has its own mode; "medium" is the default for all.
A mode sets the answer length cap, how many tool calls are allowed, how many research rounds and
sources are used, and a short instruction to the model about how wordy to be.
"""
from typing import Dict

AGENTS = ("standard", "autonomous", "subagents")
DEFAULT = "medium"

# answer_tokens: cap for follow-up answers; tool_calls: per answer; rounds/sources: multipliers on the
# research settings (at least 1 round and 3 sources are always kept)
LEVELS: Dict[str, dict] = {
    "minimal": {"answer_tokens": 450, "tool_calls": 1, "rounds": 0.34, "sources": 0.4,
                "note": "Token-saving mode (minimal): answer in as few words as possible, plain short sentences, "
                        "no introductions or recaps. Use a tool only when the answer can't be given without it."},
    "saver": {"answer_tokens": 900, "tool_calls": 2, "rounds": 0.67, "sources": 0.7,
              "note": "Token-saving mode: keep answers short and to the point, prefer one good source over many, "
                      "and avoid tool calls that aren't needed."},
    "medium": {"answer_tokens": 1800, "tool_calls": 4, "rounds": 1.0, "sources": 1.0, "note": ""},
    "detailed": {"answer_tokens": 3000, "tool_calls": 6, "rounds": 1.34, "sources": 1.3,
                 "note": "Quality mode: be thorough, check claims against more than one source, and include useful "
                         "context and nuance."},
    "max": {"answer_tokens": 4500, "tool_calls": 8, "rounds": 1.67, "sources": 1.6,
            "note": "Maximum quality mode: be comprehensive and careful, cross-check important claims, cover edge "
                    "cases, and use tools whenever they make the answer more accurate."},
}
ORDER = list(LEVELS)


def level(settings: dict, agent: str = "standard") -> str:
    v = ((settings.get("effort") or {}).get(agent)) or DEFAULT
    return v if v in LEVELS else DEFAULT


def params(settings: dict, agent: str = "standard") -> dict:
    return LEVELS[level(settings, agent)]


def scale_research(research: dict, settings: dict, agent: str = "standard") -> dict:
    """A copy of the research settings with rounds and source counts scaled for the agent's mode."""
    p = params(settings, agent)
    if p["rounds"] == 1.0 and p["sources"] == 1.0:
        return research
    r = dict(research)
    if "max_rounds" in r:
        r["max_rounds"] = max(1, round(int(r["max_rounds"]) * p["rounds"]))
    if "max_sources_total" in r:
        r["max_sources_total"] = max(3, round(int(r["max_sources_total"]) * p["sources"]))
    return r
