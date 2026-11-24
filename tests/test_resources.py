from tests import mock

mock.install(settings_patch=False)


def test_tokens_per_minute_counts_recent_calls():
    from airag import resources
    resources._tokens.clear()
    resources.note_tokens(1200)
    resources.note_tokens(300)
    resources.note_tokens(0)
    tpm = resources.tokens_per_minute()
    assert len(tpm) == 10 and tpm[-1] == 1500 and sum(tpm) == 1500


def test_snapshot_has_every_graph_value():
    from airag import resources
    d = resources.snapshot()
    for k in ("cpu", "app_mem_mb", "mem_pct", "tokens_per_min", "tokens_now", "tasks"):
        assert k in d
    assert d["app_mem_mb"] is None or d["app_mem_mb"] > 0


def test_resource_settings_default_off_and_apply_without_restart():
    from airag import config
    app = {f["key"]: f for f in config.GENERAL_SCHEMA["app"]}
    assert app["resource_graphs"]["default"] is False
    assert app["resource_style"]["default"] == "accent"
    assert ("app", "resource_graphs") in config.UI_ONLY_KEYS


def test_endpoints():
    from fastapi.testclient import TestClient
    mock.install()
    from airag.main import app
    with TestClient(app, base_url="http://127.0.0.1") as c:
        c.get("/")
        r = c.get("/api/resources").json()
        assert "tokens_per_min" in r
        p = c.post("/api/model-prices", json={"provider": "anthropic", "models": ["claude-haiku-5-5", "claude-opus-5-5"]}).json()
        assert p["prices"]["claude-haiku-5-5"] and p["prices"]["claude-opus-5-5"][1] > p["prices"]["claude-haiku-5-5"][1]
        sc = c.get("/api/schema").json()
        assert {"research", "quick", "tags"} <= {x["id"] for x in sc["tasks"]} and "anthropic" in sc["task_providers"]
