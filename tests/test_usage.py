"""Token and cost tracking."""
import asyncio

from airag import config, usage
from airag.llm.base import LLMProvider, report_usage


class Fake(LLMProvider):
    name = "anthropic"
    exact = True

    async def complete(self, system, user, max_tokens=2048, json_mode=False):
        if self.exact:
            report_usage(1000, 200)
        return "x" * 400

    async def stream(self, system, user, max_tokens=4096):
        report_usage(500)
        yield "a" * 40
        report_usage(None, 10)


def _fresh():
    usage.USAGE_FILE.unlink(missing_ok=True)


def test_exact_and_estimated_counts():
    _fresh()
    p = Fake({"model": "claude-sonnet-5-5"})
    m = usage.Metered(p)

    async def go():
        await m.complete("s", "u")
        p.exact = False
        await m.complete("s" * 40, "u" * 40)
        async for _ in m.stream("s", "u"):
            pass
    asyncio.run(go())
    row = usage.summary()["rows"][0]
    assert row["calls"] == 3
    assert row["in"] == 1000 + 20 + 500          # estimated call: 80 chars / 4
    assert row["out"] == 200 + 100 + 10
    assert row["estimated"] == 1
    assert row["cost"] > 0                        # priced from the built-in table or the online list


def test_local_models_are_free_and_unknown_flagged():
    _fresh()
    usage.add("ollama", "llama3.1:8b", 5000, 500, False)
    usage.add("openai_compatible", "some-made-up-model-xyz", 100, 100, False)
    s = usage.summary()
    assert s["spent"] == 0
    assert s["unpriced"] == ["some-made-up-model-xyz"]


def test_budget_note_and_stop():
    _fresh()
    settings = config.defaults()
    settings["usage"]["monthly_budget"] = 1
    assert usage.budget_note(settings) == ""
    usage.add("anthropic", "claude-opus-5", 100_000, 40_000, False)   # about $1.50
    assert "BUDGET" in usage.budget_note(settings)
    assert not usage.over_budget(settings)
    settings["usage"]["stop_at_budget"] = True
    assert usage.over_budget(settings)


def test_price_matching():
    usage._prices.clear()
    assert usage.per_million("anthropic", "claude-haiku-4-5-20251001") == usage.FALLBACK_PRICES["claude-haiku"]
    assert usage.per_million("pc_link", "anything") == (0.0, 0.0)
    usage._prices.update({"anthropic/claude-sonnet-5.5": (3.0, 15.0), "claude-sonnet-5-5": (3.0, 15.0)})
    assert usage.per_million("openrouter", "anthropic/claude-sonnet-5.5") == (3.0, 15.0)
    assert usage.per_million("anthropic", "claude-sonnet-5-5") == (3.0, 15.0)
    usage._prices.clear()
