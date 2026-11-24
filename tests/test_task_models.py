"""Models per task: the model picked for a task is used for that task's AI calls."""
import ast
from pathlib import Path

import pytest

from airag import config
from airag.llm import get_llm
from airag.llm.tasks import TASKS, clean_table, model_for

ROOT = Path(__file__).resolve().parent.parent


def _settings(table):
    s = config.load()
    s["llm"]["provider"] = "anthropic"
    s["llm"]["providers"].setdefault("anthropic", {})["model"] = "claude-sonnet-5-5"
    s["llm"]["task_models"] = table
    return s


def _inner(llm):
    return getattr(llm, "inner", None) or getattr(llm, "_inner", None) or getattr(llm, "provider", None) or llm


def test_main_model_when_nothing_picked():
    s = _settings({})
    assert "claude-sonnet-5-5" in get_llm(s, task="tags").describe()


def test_picked_model_used_for_its_task_only():
    s = _settings({"anthropic": {"tags": "claude-haiku-5-5"}})
    assert "claude-haiku-5-5" in get_llm(s, task="tags").describe()
    assert "claude-sonnet-5-5" in get_llm(s, task="research").describe()
    assert "claude-sonnet-5-5" in get_llm(s).describe()          # status / tests use the main model


def test_other_provider_table_ignored():
    s = _settings({"openai_compat": {"tags": "gpt-x"}})
    assert "claude-sonnet-5-5" in get_llm(s, task="tags").describe()


def test_unknown_task_fails_loudly():
    with pytest.raises(ValueError):
        model_for(_settings({}), "anthropic", "tagz")


def test_clean_table_rejects_junk():
    out = clean_table({"anthropic": {"tags": " claude-haiku-5-5 ", "nope": "x", "rewrite": "bad model;rm"},
                       "x": "notadict", 5: {}})
    assert out == {"anthropic": {"tags": "claude-haiku-5-5"}}


def test_save_replaces_table():
    config.save({"llm": {"task_models": {"anthropic": {"tags": "claude-haiku-5-5", "summary": "claude-haiku-5-5"}}}})
    config.save({"llm": {"task_models": {"anthropic": {"tags": "claude-haiku-5-5"}}}})
    assert config.load()["llm"]["task_models"] == {"anthropic": {"tags": "claude-haiku-5-5"}}
    config.save({"llm": {"task_models": {}}})
    assert config.load()["llm"]["task_models"] == {}


def test_every_ai_call_names_a_known_task():
    """Call sites must pass task=...; status/list-models/test-connection in main.py use the main model."""
    allowed_bare = {("main.py", "status"), ("main.py", "models"), ("main.py", "test_llm")}
    for path in (ROOT / "airag").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for fn in [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
            for call in [c for c in ast.walk(fn) if isinstance(c, ast.Call)]:
                if getattr(call.func, "id", None) != "get_llm":
                    continue
                kw = {k.arg: k.value for k in call.keywords}
                if "task" not in kw:
                    assert (path.name, fn.name) in allowed_bare, f"{path.name}:{fn.name} calls get_llm without a task"
                    continue
                v = kw["task"]
                if isinstance(v, ast.Constant):
                    assert v.value in TASKS, f"{path.name}: unknown task {v.value!r}"
