"""LLM provider registry.

To add a provider: create a module with a subclass of LLMProvider decorated
with @register, then import it at the bottom of this file.
"""
from __future__ import annotations

from typing import Dict, Type

from .base import LLMError, LLMProvider

PROVIDERS: Dict[str, Type[LLMProvider]] = {}


def register(cls: Type[LLMProvider]) -> Type[LLMProvider]:
    PROVIDERS[cls.name] = cls
    return cls


def get_llm(settings: dict) -> LLMProvider:
    llm = settings["llm"]
    name = llm.get("provider", "")
    cls = PROVIDERS.get(name)
    if cls is None:
        raise LLMError(f"Unknown AI provider '{name}'. Pick one in Settings.")
    cfg = {f["key"]: f.get("default", "") for f in cls.fields}
    cfg.update(llm.get("providers", {}).get(name, {}))
    return cls(cfg, temperature=float(llm.get("temperature", 0.3)))


# Registration order = order shown in the UI.
from . import ollama, anthropic_provider, openai_compat  # noqa: E402,F401
