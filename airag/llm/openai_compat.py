"""OpenAI chat-completions API and everything compatible with it
(DeepSeek, LM Studio, vLLM, OpenRouter, llama.cpp server, Groq, ...)."""
from __future__ import annotations

import json
from typing import AsyncIterator, List

import httpx

from . import register
from .base import LLMError, LLMProvider, http_timeout, short_error, strip_think


class _OpenAIBase(LLMProvider):
    requires_key = False
    supports_json_mode = False
    use_max_completion_tokens = False

    def _is_reasoning(self) -> bool:
        m = self.model.lower()
        return m.startswith(("o1", "o3", "o4", "gpt-5")) or "reasoner" in m

    def _url(self, path: str) -> str:
        return str(self.cfg.get("base_url") or "").rstrip("/") + path

    def _headers(self) -> dict:
        key = self.cfg.get("api_key")
        if self.requires_key and not key:
            raise LLMError(f"Add your {self.label} API key in Settings → Model.")
        h = {"Content-Type": "application/json"}
        if key:
            h["Authorization"] = f"Bearer {key}"
        return h

    def _body(self, system, user, max_tokens, stream, json_mode, compat=False) -> dict:
        if not self.model:
            raise LLMError(f"No {self.label} model selected (Settings → Model).")
        body = {"model": self.model,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        reasoning = self._is_reasoning()
        if reasoning:
            max_tokens = max(max_tokens * 4, 8000)  # reasoning tokens count against the budget
        body["max_completion_tokens" if self.use_max_completion_tokens else "max_tokens"] = max_tokens
        if not compat:
            if not reasoning:
                body["temperature"] = self.temperature
            if json_mode and self.supports_json_mode:
                body["response_format"] = {"type": "json_object"}
        if stream:
            body["stream"] = True
        return body

    async def complete(self, system, user, max_tokens=2048, json_mode=False) -> str:
        headers = self._headers()
        async with httpx.AsyncClient(timeout=http_timeout(900)) as c:
            for compat in (False, True):
                try:
                    r = await c.post(self._url("/chat/completions"), headers=headers,
                                     json=self._body(system, user, max_tokens, False, json_mode, compat))
                except httpx.ConnectError:
                    raise LLMError(f"Can't reach {self._url('')}")
                except httpx.HTTPError as e:
                    raise LLMError(f"{self.label} request failed: {e!r}")
                if r.status_code == 400 and not compat:
                    continue  # retry without temperature / response_format
                if r.status_code >= 400:
                    raise LLMError(f"{self.label} " + short_error(r.status_code, r.text))
                msg = r.json()["choices"][0]["message"]
                return strip_think(msg.get("content") or "")
        raise LLMError(f"{self.label} request failed")

    async def stream(self, system, user, max_tokens=4096) -> AsyncIterator[str]:
        headers = self._headers()
        async with httpx.AsyncClient(timeout=http_timeout(900)) as c:
            for compat in (False, True):
                async with c.stream("POST", self._url("/chat/completions"), headers=headers,
                                    json=self._body(system, user, max_tokens, True, False, compat)) as r:
                    if r.status_code >= 400:
                        text = (await r.aread()).decode(errors="replace")
                        if r.status_code == 400 and not compat:
                            continue
                        raise LLMError(f"{self.label} " + short_error(r.status_code, text))
                    async for line in r.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            d = json.loads(data)
                        except ValueError:
                            continue
                        choices = d.get("choices") or []
                        if choices:
                            piece = (choices[0].get("delta") or {}).get("content")
                            if piece:
                                yield piece
                    return

    async def list_models(self) -> List[str]:
        async with httpx.AsyncClient(timeout=http_timeout(20)) as c:
            try:
                r = await c.get(self._url("/models"), headers=self._headers())
            except httpx.HTTPError:
                raise LLMError(f"Can't reach {self._url('')}")
        if r.status_code >= 400:
            raise LLMError(f"{self.label} " + short_error(r.status_code, r.text))
        return sorted(m["id"] for m in r.json().get("data", []))


@register
class OpenAI(_OpenAIBase):
    name = "openai"
    label = "OpenAI"
    requires_key = True
    supports_vision = True

    def vision_content(self, text, image_urls):
        return [{"type": "text", "text": text}] + [{"type": "image_url", "image_url": {"url": u, "detail": "low"}}
                                                    for u in image_urls]

    supports_json_mode = True
    use_max_completion_tokens = True
    fields = [
        {"key": "api_key", "label": "API key", "type": "secret", "default": "", "env": "OPENAI_API_KEY"},
        {"key": "model", "label": "Model", "type": "model", "default": "gpt-5-mini"},
        {"key": "base_url", "label": "API URL", "type": "url", "default": "https://api.openai.com/v1"},
    ]


@register
class DeepSeek(_OpenAIBase):
    name = "deepseek"
    label = "DeepSeek"
    requires_key = True
    supports_json_mode = True
    fields = [
        {"key": "api_key", "label": "API key", "type": "secret", "default": "", "env": "DEEPSEEK_API_KEY"},
        {"key": "model", "label": "Model", "type": "model", "default": "deepseek-chat",
         "help": "deepseek-chat (fast) or deepseek-reasoner (slower, thinks first)."},
        {"key": "base_url", "label": "API URL", "type": "url", "default": "https://api.deepseek.com/v1"},
    ]


@register
class OpenAICompatible(_OpenAIBase):
    name = "openai_compatible"
    label = "OpenAI-compatible server"
    fields = [
        {"key": "base_url", "label": "API URL", "type": "url", "default": "http://localhost:1234/v1",
         "help": "LM Studio, vLLM, llama.cpp, OpenRouter (https://openrouter.ai/api/v1), Groq, ..."},
        {"key": "api_key", "label": "API key (if needed)", "type": "secret", "default": ""},
        {"key": "model", "label": "Model", "type": "model", "default": ""},
    ]


@register
class PcLink(_OpenAIBase):
    """The Ollama models on the user's own PC, shared with Settings → AI model → Share with my phone."""
    name = "pc_link"
    label = "My PC (Ollama)"
    requires_key = True
    fields = [
        {"key": "base_url", "label": "PC address", "type": "text", "default": "",
         "help": "Shown on the PC under Settings → AI model → Share with my phone, e.g. 192.168.1.20:47120"},
        {"key": "api_key", "label": "Pairing code", "type": "secret", "default": ""},
        {"key": "model", "label": "Model", "type": "model", "default": ""},
    ]

    def _url(self, path: str) -> str:
        addr = str(self.cfg.get("base_url") or "").strip().rstrip("/")
        if not addr:
            raise LLMError("Enter your PC's address (Settings → AI model).")
        if "://" not in addr:
            addr = "http://" + addr
        if not addr.endswith("/v1"):
            addr += "/v1"
        return addr + path

    def _headers(self) -> dict:
        key = str(self.cfg.get("api_key") or "").strip().upper()
        if not key:
            raise LLMError("Enter the pairing code shown on your PC (Settings → AI model).")
        return {"Content-Type": "application/json", "Authorization": f"Bearer {key}"}
