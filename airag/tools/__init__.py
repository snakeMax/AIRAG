"""Tools the AI agents can ask the app to use.

An agent never runs anything itself. It writes one line, e.g.
    TOOL {"name": "calculator", "args": {"expression": "solve(x**2 - 4, x)"}}
and the backend checks that the tool exists, that THIS agent type may use it (Settings -> Tools),
and that the arguments have the right shape; then it runs the tool and gives back a short result,
marked as data. Each tool is a small entry in REGISTRY, so tools are easy to add or remove.

Agent types: "standard" (the normal research assistant), "autonomous" and "subagents" (0.5).
The standard agent can't ask for more tools or for settings changes: when a tool isn't enabled it
answers by reasoning in plain text instead.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Dict, List, Optional

AGENTS = ("standard", "autonomous", "subagents")


@dataclass
class Tool:
    name: str
    summary: str                     # what the model is told
    args: Dict[str, str]             # name -> "str" | "int" (all optional unless in `required`)
    run: Callable[..., Awaitable[str]]
    required: tuple = ()
    label: str = ""                  # shown in Settings -> Tools
    help: str = ""
    costly: bool = False             # uses noticeably more tokens or network
    client: bool = False             # the app does it (read aloud, start a job...), not the server
    defaults: tuple = AGENTS         # agent types it's on for by default
    later: bool = False              # not usable yet (planned for 0.5)


REGISTRY: Dict[str, Tool] = {}


def register(tool: Tool) -> Tool:
    REGISTRY[tool.name] = tool
    return tool


def default_sets() -> Dict[str, List[str]]:
    return {a: [t.name for t in REGISTRY.values() if a in t.defaults] for a in AGENTS}


def enabled(settings: dict, agent: str) -> List[str]:
    sets = (settings.get("agent_tools") or {}).get("sets") or {}
    names = sets.get(agent)
    if names is None:
        names = default_sets()[agent]
    return [n for n in names if n in REGISTRY and not REGISTRY[n].later]


def describe(names: List[str]) -> str:
    """The tool list as the model sees it."""
    lines = []
    for n in names:
        t = REGISTRY[n]
        args = ", ".join(f'"{k}": {v}' for k, v in t.args.items())
        lines.append(f'- {n} {{{args}}}: {t.summary}')
    return "\n".join(lines) or "(none)"


def parse_call(text: str) -> Optional[dict]:
    """A model reply that starts with a tool request -> {"name", "args"}; anything else -> None.
    Anything the model wrote after the request is ignored."""
    t = text.strip().strip("`").lstrip()
    if not t.startswith("TOOL"):
        return None
    rest = t[4:].lstrip(" :")
    start = rest.find("{")
    if start < 0:
        return {"name": "", "args": {}, "bad": "A TOOL line needs JSON after it."}
    try:
        data, _ = json.JSONDecoder().raw_decode(rest[start:])
    except ValueError:
        return {"name": "", "args": {}, "bad": "The TOOL line wasn't valid JSON."}
    if not isinstance(data, dict) or not isinstance(data.get("name"), str):
        return {"name": "", "args": {}, "bad": "A TOOL line needs a name."}
    args = data.get("args") if isinstance(data.get("args"), dict) else {}
    return {"name": data["name"], "args": args}


@dataclass
class Session:
    """One conversation's tool use: what's allowed, what was refused (so it isn't asked again)."""
    agent: str
    allowed: List[str]
    ctx: dict
    calls: int = 0
    max_calls: int = 4
    refused: Dict[str, str] = field(default_factory=dict)
    client_actions: List[dict] = field(default_factory=list)

    async def call(self, req: dict) -> str:
        name = req.get("name", "")
        if req.get("bad"):
            return f"Tool request not understood: {req['bad']} Answer without tools if you can."
        if name in self.refused:
            return f"{name} is not available ({self.refused[name]}). Don't ask for it again; reason it out in text."
        tool = REGISTRY.get(name)
        if tool is None or tool.later or name not in self.allowed:
            why = "it doesn't exist" if tool is None else "it's switched off for this assistant in Settings -> Tools"
            self.refused[name] = why
            return (f"{name} is not available ({why}). Don't ask for it again. Work it out by reasoning in plain text, "
                    "and say briefly that you did so without the tool.")
        if self.calls >= self.max_calls:
            return "Tool limit reached for this answer. Finish the answer with what you have."
        args = {}
        for k, typ in tool.args.items():
            if k in req["args"]:
                v = req["args"][k]
                args[k] = int(v) if typ == "int" and str(v).lstrip("-").isdigit() else str(v)[:4000]
        missing = [k for k in tool.required if not args.get(k)]
        if missing:
            return f"{name} needs: {', '.join(missing)}."
        self.calls += 1
        try:
            return (await tool.run(self, **args))[:6000]
        except Exception as e:      # a broken tool must never break the answer
            return f"{name} failed: {e}. Continue without it."


from . import builtin  # noqa: E402,F401  (registers the tools)
