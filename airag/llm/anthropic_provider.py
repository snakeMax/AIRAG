from __future__ import annotations

import json
from typing import AsyncIterator, List

import httpx

from . import register
from .base import LLMError, LLMProvider, http_timeout, report_usage, short_error, strip_think


@register
class Anthropic(LLMProvider):
    name = "anthropic"
    label = "Anthropic Claude"
    fields = [
        {"key": "api_key", "label": "API key", "type": "secret", "default": "", "env": "ANTHROPIC_API_KEY",
         "help": "From console.anthropic.com. Or set the ANTHROPIC_API_KEY environment variable."},
        {"key": "model", "label": "Model", "type": "model", "default": "claude-sonnet-5-5",
         "help": "Click 'Load models' to see what your key can use."},
        {"key": "base_url", "label": "API URL", "type": "url", "default": "https://api.anthropic.com"},
    ]

    def _headers(self) -> dict:
        key = self.cfg.get("api_key")
        if not key:
            raise LLMError("Add your Anthropic API key in Settings → Model.")
        return {"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"}

    def _url(self, path: str) -> str:
        return str(self.cfg.get("base_url") or "https://api.anthropic.com").rstrip("/") + path

    supports_vision = True

    def vision_content(self, text, image_urls):
        return [{"type": "text", "text": text}] + [{"type": "image", "source": {"type": "url", "url": u}}
                                                    for u in image_urls]

    def _body(self, system, user, max_tokens, stream, temperature=True) -> dict:
        body = {"model": self.model, "max_tokens": max_tokens, "system": system,
                "messages": [{"role": "user", "content": user}]}
        if temperature:
            body["temperature"] = self.temperature
        if stream:
            body["stream"] = True
        return body

    async def complete(self, system, user, max_tokens=2048, json_mode=False) -> str:
        headers = self._headers()
        async with httpx.AsyncClient(timeout=http_timeout(600)) as c:
            for use_temp in (True, False):
                try:
                    r = await c.post(self._url("/v1/messages"), headers=headers,
                                     json=self._body(system, user, max_tokens, False, use_temp))
                except httpx.HTTPError as e:
                    raise LLMError(f"Anthropic request failed: {e!r}")
                if r.status_code == 400 and use_temp and "temperature" in r.text:
                    continue
                if r.status_code >= 400:
                    raise LLMError("Anthropic " + short_error(r.status_code, r.text))
                data = r.json()
                u = data.get("usage") or {}
                report_usage(u.get("input_tokens"), u.get("output_tokens"))
                return strip_think("".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"))
        raise LLMError("Anthropic request failed")

    async def stream(self, system, user, max_tokens=4096) -> AsyncIterator[str]:
        headers = self._headers()
        async with httpx.AsyncClient(timeout=http_timeout(600)) as c:
            for use_temp in (True, False):
                async with c.stream("POST", self._url("/v1/messages"), headers=headers,
                                    json=self._body(system, user, max_tokens, True, use_temp)) as r:
                    if r.status_code >= 400:
                        text = (await r.aread()).decode(errors="replace")
                        if r.status_code == 400 and use_temp and "temperature" in text:
                            continue
                        raise LLMError("Anthropic " + short_error(r.status_code, text))
                    async for line in r.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        try:
                            d = json.loads(line[5:].strip())
                        except ValueError:
                            continue
                        if d.get("type") == "message_start":
                            report_usage(((d.get("message") or {}).get("usage") or {}).get("input_tokens"))
                        elif d.get("type") == "message_delta" and d.get("usage"):
                            report_usage(None, d["usage"].get("output_tokens"))
                        elif d.get("type") == "content_block_delta" and d.get("delta", {}).get("type") == "text_delta":
                            yield d["delta"].get("text", "")
                        elif d.get("type") == "error":
                            raise LLMError(f"Anthropic: {d.get('error', {}).get('message', d)}")
                    return

    async def list_models(self) -> List[str]:
        async with httpx.AsyncClient(timeout=http_timeout(20)) as c:
            r = await c.get(self._url("/v1/models?limit=100"), headers=self._headers())
        if r.status_code >= 400:
            raise LLMError("Anthropic " + short_error(r.status_code, r.text))
        return [m["id"] for m in r.json().get("data", [])]
