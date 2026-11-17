from __future__ import annotations

import re
from typing import AsyncIterator, List

import httpx


class LLMError(Exception):
    """A user-facing problem with the AI provider (bad key, unreachable, ...)."""


_THINK = re.compile(r"<think>.*?(</think>|$)", re.S | re.I)


def strip_think(text: str) -> str:
    """Remove <think>…</think> blocks emitted by reasoning models (DeepSeek-R1, Qwen3…)."""
    return _THINK.sub("", text or "").strip()


def http_timeout(read: float = 300) -> httpx.Timeout:
    return httpx.Timeout(read, connect=15)


def short_error(status: int, body: str) -> str:
    body = (body or "").strip().replace("\n", " ")
    return f"HTTP {status}: {body[:300]}"


class LLMProvider:
    name = "base"
    label = "Base provider"
    # Settings fields rendered in the UI. Types: text, url, secret, number, select, bool, model
    fields: List[dict] = []

    def __init__(self, cfg: dict, temperature: float = 0.3):
        self.cfg = cfg
        self.temperature = temperature
        self.model = str(cfg.get("model") or "").strip()

    def describe(self) -> str:
        return f"{self.label} · {self.model or 'no model'}"

    async def complete(self, system: str, user: str, max_tokens: int = 2048,
                       json_mode: bool = False) -> str:
        raise NotImplementedError

    async def stream(self, system: str, user: str, max_tokens: int = 4096) -> AsyncIterator[str]:
        """Yield text chunks. Default: one chunk from complete()."""
        yield await self.complete(system, user, max_tokens)

    async def list_models(self) -> List[str]:
        return []
