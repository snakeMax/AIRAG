from __future__ import annotations

import json
import re
from typing import Any

from .base import LLMError, LLMProvider, strip_think

_FENCE = re.compile(r"```(?:json)?", re.I)


def extract_json(text: str) -> Any:
    t = _FENCE.sub("", strip_think(text)).strip()
    dec = json.JSONDecoder()
    for i, ch in enumerate(t):
        if ch == "{":
            try:
                obj, _ = dec.raw_decode(t[i:])
                return obj
            except ValueError:
                continue
    raise ValueError("no JSON object found in model reply")


async def complete_json(llm: LLMProvider, system: str, user: str,
                        max_tokens: int = 1500, retries: int = 1) -> dict:
    system = system + "\n\nRespond with ONE valid JSON object and nothing else."
    last: Exception = ValueError("empty reply")
    prompt = user
    for _ in range(retries + 1):
        reply = await llm.complete(system, prompt, max_tokens=max_tokens, json_mode=True)
        try:
            obj = extract_json(reply)
            if isinstance(obj, dict):
                return obj
        except ValueError as e:
            last = e
        prompt = user + "\n\nIMPORTANT: your previous reply was not valid JSON. Reply with ONLY the JSON object."
    raise LLMError(f"The model did not return valid JSON ({last}). Try a larger/more capable model.")
