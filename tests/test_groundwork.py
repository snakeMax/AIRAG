from tests import mock

mock.install(settings_patch=False)


def test_agent_types_match_tool_sets_and_limits_are_clamped():
    from airag import agents
    from airag.tools import AGENTS
    assert set(agents.TYPES) == set(AGENTS)
    assert agents.available("0.4.2") == ["standard"]
    assert set(agents.available("0.5.0")) == set(AGENTS)
    lim = agents.Limits.from_settings({"agents": {"subagents": 99, "max_tool_calls": 500, "cost_cap": "x", "retries": -3}})
    assert lim.subagents == agents.MAX_SUBAGENTS and lim.max_tool_calls == agents.MAX_TOOL_CALLS
    assert lim.cost_cap == agents.DEFAULT_COST_CAP and lim.retries == 0


def test_agent_tasks_are_known_model_tasks():
    from airag import agents
    from airag.llm import tasks
    for a in agents.TYPES.values():
        assert a.task in tasks.TASKS


def test_personal_editions_are_unchanged(monkeypatch):
    from airag import editions
    monkeypatch.delenv("AIRAG_EDITION", raising=False)
    assert editions.edition() in editions.PERSONAL
    assert editions.current_user().admin and editions.allowed("export")
    monkeypatch.setenv("AIRAG_EDITION", "enterprise")
    if editions.edition() == "enterprise":     # (not on Android)
        assert editions.is_enterprise()


def test_groundwork_settings_have_defaults():
    from airag import config
    d = config.defaults()
    assert d["agents"]["subagents"] == 1 and d["agents"]["cost_cap"] == 1.0
    assert d["enterprise"]["server_url"] == ""
