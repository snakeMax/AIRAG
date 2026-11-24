"""Agents (groundwork for 0.5.0 "The Agentic Utilities Update").

Only the shapes live here for now: which agent types exist, their limits and the interface every agent
will implement. Nothing in this package runs an agent yet; the standard research assistant keeps working
as before (airag.pipeline / airag.followup). 0.5.0 fills in `autonomous.py` and `subagents.py`.

Rules the implementations must keep (see the development plan):
- every agent runs as a job through airag.runs (queued, shown in the activity bar / History / Android
  notification), with its own settings copy (config.begin_job) and live keys only between steps;
- tools only through airag.tools (structured request -> validated against that agent's tool set -> fenced
  result); never shell, code, SQL, files outside picked folders, API keys or sending anything anywhere;
- budget checked on every AI call; hard limits on steps, tool calls, sub-agents and time.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Protocol

from ..tools import AGENTS as TOOL_AGENT_TYPES

# hard limits (code constants; settings may lower them, never raise them)
MAX_SUBAGENTS = 10
MAX_TOOL_CALLS = 25
MAX_STEPS = 60
DEFAULT_RETRIES = 2
DEFAULT_TOOL_TIMEOUT = 30          # seconds
DEFAULT_COST_CAP = 1.00            # $ per autonomous session
DEFAULT_TOKEN_SHARE_SUBAGENTS = 0.70


@dataclass(frozen=True)
class AgentType:
    id: str                         # matches the tool-set names in airag.tools.AGENTS
    label: str
    available_from: str             # app version that runs it
    can_request_tools: bool         # may ask the user for more tools (once per permission per session)
    can_start_subagents: bool
    task: str                       # model task (airag.llm.tasks) its AI calls use


TYPES: Dict[str, AgentType] = {
    "standard": AgentType("standard", "Research assistant", "0.4.0", False, False, "followup"),
    "autonomous": AgentType("autonomous", "Autonomous agent", "0.5.0", True, True, "research"),
    "subagents": AgentType("subagents", "Sub-agents", "0.5.0", False, False, "research"),
}


def available(app_version: str) -> List[str]:
    """Agent types this version can run."""
    def key(v: str):
        return tuple(int(x) for x in v.split(".")[:3] if x.isdigit())
    return [k for k, a in TYPES.items() if key(app_version) >= key(a.available_from)]


@dataclass
class Limits:
    """Per-session limits, taken from settings and clamped to the hard limits."""
    max_steps: int = 30
    max_tool_calls: int = MAX_TOOL_CALLS
    retries: int = DEFAULT_RETRIES
    tool_timeout: int = DEFAULT_TOOL_TIMEOUT
    cost_cap: float = DEFAULT_COST_CAP
    token_limit: int = 0            # 0 = only the cost cap and the monthly budget
    subagents: int = 1
    subagent_token_share: float = DEFAULT_TOKEN_SHARE_SUBAGENTS

    @classmethod
    def from_settings(cls, settings: dict) -> "Limits":
        a = (settings or {}).get("agents") or {}

        def num(k, default, lo, hi, kind=int):
            try:
                v = kind(a.get(k, default))
            except (TypeError, ValueError):
                v = default
            return max(lo, min(hi, v))
        return cls(
            max_steps=num("max_steps", 30, 1, MAX_STEPS),
            max_tool_calls=num("max_tool_calls", MAX_TOOL_CALLS, 1, MAX_TOOL_CALLS),
            retries=num("retries", DEFAULT_RETRIES, 0, 5),
            tool_timeout=num("tool_timeout", DEFAULT_TOOL_TIMEOUT, 5, 120),
            cost_cap=num("cost_cap", DEFAULT_COST_CAP, 0.0, 50.0, float),
            token_limit=num("token_limit", 0, 0, 5_000_000),
            subagents=num("subagents", 1, 0, MAX_SUBAGENTS),
            subagent_token_share=num("subagent_token_share", DEFAULT_TOKEN_SHARE_SUBAGENTS, 0.1, 0.9, float),
        )


@dataclass
class Step:
    """One recorded step of an agent session (for the "How I researched this" log and Undo)."""
    kind: str                        # "think" | "tool" | "write" | "ask_user" | "spawn" | "note"
    text: str = ""
    tool: Optional[str] = None
    ok: bool = True
    data: dict = field(default_factory=dict)


class Agent(Protocol):
    """What every agent implements (0.5.0). Runs inside a job; `emit` streams events to the page."""
    type: AgentType
    limits: Limits

    async def run(self, goal: str, emit) -> dict: ...
    async def cancel(self, keep_progress: bool = True) -> None: ...


assert set(TYPES) == set(TOOL_AGENT_TYPES), "agent types and tool sets must match"
