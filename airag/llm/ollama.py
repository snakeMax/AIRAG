from __future__ import annotations

import json
from typing import AsyncIterator, List

import httpx

from . import register
from .base import LLMError, LLMProvider, http_timeout, short_error, strip_think


@register
class Ollama(LLMProvider):
    name = "ollama"
    label = "Ollama (local)"
    fields = [
        {"key": "base_url", "label": "Ollama URL", "type": "url", "default": "http://localhost:11434"},
        {"key": "model", "label": "Model", "type": "model", "default": "llama3.1:8b",
         "help": "Any model you've pulled, e.g. qwen2.5:14b, llama3.1:8b, mistral-nemo."},
        {"key": "num_ctx", "label": "Context window (tokens)", "type": "number", "default": 16384,
         "min": 2048, "max": 262144, "step": 1024, "help": "Bigger = more source text fits, but needs more RAM/VRAM."},
        {"key": "autostart", "label": "Start Ollama automatically when AIRAG needs it", "type": "bool", "default": False,
         "help": "Off by default so Ollama only uses memory when you choose. You can always start it from this page."},
        {"key": "think", "label": "Let 'thinking' models think before answering", "type": "bool", "default": False,
         "help": "Slower, sometimes better. Only affects models that support it (Qwen3, DeepSeek-R1, gpt-oss...)."},
    ]

    def _url(self, path: str) -> str:
        return str(self.cfg.get("base_url") or "http://localhost:11434").rstrip("/") + path

    def _body(self, system: str, user: str, max_tokens: int, stream: bool, json_mode: bool) -> dict:
        if not self.model:
            raise LLMError("No Ollama model selected (Settings → Model).")
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "stream": stream,
            "options": {"temperature": self.temperature, "num_ctx": int(self.cfg.get("num_ctx") or 16384),
                        "num_predict": max_tokens},
        }
        if json_mode:
            body["format"] = "json"
        if not self.cfg.get("think"):
            body["think"] = False
        return body

    async def _ensure(self) -> None:
        """Start Ollama if allowed; raise a friendly error if it can't be reached."""
        from ..ollama_manager import ensure_running
        if self.cfg.get("autostart", False) and await ensure_running(self._url("")):
            return
        raise self._unreachable()

    @staticmethod
    def _think_unsupported(text: str) -> bool:
        return "think" in (text or "").lower()

    def _unreachable(self) -> LLMError:
        return LLMError(f"Ollama isn't running at {self._url('')}. Start it in Settings → AI model "
                        "(or turn on 'Start Ollama automatically').")

    async def complete(self, system, user, max_tokens=2048, json_mode=False) -> str:
        body = self._body(system, user, max_tokens, False, json_mode)
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=http_timeout(900)) as c:
                    r = await c.post(self._url("/api/chat"), json=body)
            except httpx.ConnectError:
                if attempt:
                    raise self._unreachable()
                await self._ensure()
                continue
            except httpx.HTTPError as e:
                raise LLMError(f"Ollama request failed: {e!r}")
            if r.status_code == 400 and "think" in body and self._think_unsupported(r.text):
                body.pop("think")
                continue
            if r.status_code == 404 and "not found" in r.text.lower():
                raise LLMError(f"The model '{self.model}' isn't downloaded in Ollama. Pick or download one in Settings → AI model.")
            if r.status_code >= 400:
                raise LLMError("Ollama " + short_error(r.status_code, r.text))
            return strip_think(r.json().get("message", {}).get("content", ""))
        raise self._unreachable()

    async def stream(self, system, user, max_tokens=4096) -> AsyncIterator[str]:
        body = self._body(system, user, max_tokens, True, False)
        if not await self._reachable():
            await self._ensure()
        try:
            async with httpx.AsyncClient(timeout=http_timeout(900)) as c:
                async with c.stream("POST", self._url("/api/chat"), json=body) as r:
                    if r.status_code == 400 and "think" in body:
                        body.pop("think")
                        await r.aread()
                        async for piece in self.stream_body(c, body):
                            yield piece
                        return
                    if r.status_code >= 400:
                        raise LLMError("Ollama " + short_error(r.status_code, (await r.aread()).decode(errors="replace")))
                    async for line in r.aiter_lines():
                        if not line.strip():
                            continue
                        d = json.loads(line)
                        if d.get("error"):
                            raise LLMError(f"Ollama: {d['error']}")
                        piece = d.get("message", {}).get("content", "")
                        if piece:
                            yield piece
                        if d.get("done"):
                            break
        except httpx.ConnectError:
            raise self._unreachable()

    async def _reachable(self) -> bool:
        from ..ollama_manager import version
        return bool(await version(self._url("")))

    async def stream_body(self, c, body) -> AsyncIterator[str]:
        async with c.stream("POST", self._url("/api/chat"), json=body) as r:
            if r.status_code >= 400:
                raise LLMError("Ollama " + short_error(r.status_code, (await r.aread()).decode(errors="replace")))
            async for line in r.aiter_lines():
                if line.strip():
                    d = json.loads(line)
                    if d.get("error"):
                        raise LLMError(f"Ollama: {d['error']}")
                    piece = d.get("message", {}).get("content", "")
                    if piece:
                        yield piece
                    if d.get("done"):
                        break

    async def list_models(self) -> List[str]:
        if self.cfg.get("autostart", False) and not await self._reachable():
            await self._ensure()
        try:
            async with httpx.AsyncClient(timeout=http_timeout(15)) as c:
                r = await c.get(self._url("/api/tags"))
        except httpx.HTTPError:
            raise self._unreachable()
        r.raise_for_status()
        return sorted(m["name"] for m in r.json().get("models", []))
