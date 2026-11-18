"""Guarded execution: running tasks keep their settings; small ones change from the next step; things that
would disturb a running task wait."""
import asyncio

import pytest

from airag import config, runs


def _set(**app):
    config.save({"app": app})


def test_task_keeps_its_settings_and_live_keys_follow():
    _set(guarded_execution=True)
    config.save({"research": {"results_per_query": 8}, "llm": {"provider": "mock"}})
    seen = {}

    async def task():
        token = config.begin_job()
        try:
            s = config.load()
            config.save({"llm": {"provider": "ollama"}, "research": {"results_per_query": 3}})   # changed mid-task
            seen["provider"] = config.load()["llm"]["provider"]       # vital: unchanged for this task
            seen["live_before"] = config.load()["research"]["results_per_query"]
            s = config.live_update(s)                                 # next step
            seen["live_after"] = s["research"]["results_per_query"]
            seen["helpers_see"] = config.load()["research"]["results_per_query"]
        finally:
            config.end_job(token)
        seen["after_task"] = config.load()["llm"]["provider"]

    asyncio.run(task())
    assert seen == {"provider": "mock", "live_before": 8, "live_after": 3, "helpers_see": 3, "after_task": "ollama"}
    config.save({"llm": {"provider": "mock"}, "research": {"results_per_query": 8}})


def test_unguarded_reads_live():
    _set(guarded_execution=False)
    try:
        async def task():
            token = config.begin_job()
            assert token is None
            config.save({"research": {"max_rounds": 2}})
            return config.load()["research"]["max_rounds"]
        assert asyncio.run(task()) == 2
    finally:
        _set(guarded_execution=True)
        config.save({"research": {"max_rounds": 3}})


def test_bad_live_value_is_ignored():
    _set(guarded_execution=True)
    cur = config.load()
    raw = config.load_raw()
    raw.setdefault("research", {})["results_per_query"] = "lots"
    from airag import paths
    import json
    paths.atomic_write_text(config.SETTINGS_PATH, json.dumps(raw))
    out = config.live_update(cur)
    assert isinstance(out["research"]["results_per_query"], int)
    config.save({"research": {"results_per_query": 8}})


def test_changed_for_running():
    a = config.load()
    b = config.load()
    b["research"]["results_per_query"] = 2          # live: not reported
    b["audio"]["volume"] = 0.1                      # UI only: not reported
    assert config.changed_for_running(a, b) == []
    b["llm"]["provider"] = "ollama"
    assert config.changed_for_running(a, b) == ["llm"]


def test_clearing_waits_for_running_tasks(monkeypatch):
    from fastapi.testclient import TestClient
    from airag.main import app
    c = TestClient(app, base_url="http://127.0.0.1")
    c.get("/")
    _set(guarded_execution=True)
    busy = [object()]
    monkeypatch.setattr(runs, "active", lambda kinds=None: busy)
    r = c.post("/api/app/clear-cache")
    assert r.status_code == 409 and "Guarded execution" in r.json()["detail"]
    assert c.post("/api/library/clear").status_code == 409
    assert c.delete("/api/history").status_code == 409
    out = c.post("/api/settings", json={"llm": {"provider": "ollama"}}).json()
    assert out["_applies_later"] == ["llm"]
    c.post("/api/settings", json={"llm": {"provider": "mock"}})
    _set(guarded_execution=False)
    from airag import paths
    monkeypatch.setattr(paths, "ANDROID", False)          # no WebView to clear in a test
    try:
        assert c.post("/api/app/clear-cache").status_code == 200        # allowed; the task just reads pages again
    finally:
        _set(guarded_execution=True)


def test_search_survives_settings_changes_mid_run(monkeypatch):
    """A real (mock) search: the AI model and offline mode change halfway; it still finishes with its sources."""
    from tests import mock
    mock.install()
    from airag import pipeline
    _set(guarded_execution=True)
    real_round = pipeline.Research.read_round
    changed = {}

    async def read_round(self, rnd, fresh):
        out = await real_round(self, rnd, fresh)
        if not changed:
            changed["x"] = True
            config.save({"library": {"offline": True}, "llm": {"provider": "nonexistent"}, "research": {"max_rounds": 1}})
        return out
    monkeypatch.setattr(pipeline.Research, "read_round", read_round)

    async def go():
        token = config.begin_job()
        try:
            r = pipeline.Research("hummingbird wing beats", "article", config.load(), _noop)
            return await r.run()
        finally:
            config.end_job(token)
    try:
        rec = asyncio.run(go())
        assert rec.get("article") and rec.get("sources")
    finally:
        config.save({"library": {"offline": False}, "llm": {"provider": "mock"}, "research": {"max_rounds": 3}})


async def _noop(ev):
    return None
