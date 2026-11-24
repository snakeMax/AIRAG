import asyncio

import pytest

from tests import mock

mock.install(settings_patch=False)


@pytest.fixture
def SV(tmp_path):
    from airag.notes import index, store
    s = {"notes": {"root": str(tmp_path / "Notes")}, "llm": {"provider": "anthropic"}}
    v = store.create_vault(s, "Moose", "research")
    store.create_note(s, v, "Topics", "Moose and roads", "Collisions on roads with fences.\n", {"type": "topic", "tags": ["roads"]})
    store.create_note(s, v, "Sources", "Fence study 2019", "Fences halve moose collisions.\n", {"type": "source"})
    index.update(s, v)
    return s, v


def test_candidates_find_related_notes(SV):
    from airag.notes import organize
    s, v = SV
    got = [n["title"] for n in organize.candidates(s, v, "Saw a moose by the road fence today")]
    assert "Moose and roads" in got


def test_check_keeps_only_what_fits_the_vault(SV):
    from airag.notes import organize
    s, v = SV
    ctx = organize.context(s, v, "moose fence roads")
    raw = {"title": "Moose / fence: notes?", "folder": "../../etc", "type": "spaceship",
           "tags": ["Roads", "#wild life", "123", "ok/nested", "<script>"],
           "body": "Seen near [[Moose and roads]] and [[Made up note|a made up note]] and [[Fence study 2019#Results]].",
           "why": "x" * 500}
    out = organize.check(raw, ctx, "moose fence roads")
    assert out["folder"] == "Inbox"                       # unknown folder -> Inbox
    assert out["type"] == ""                              # not one of the vault's types
    assert out["tags"] == ["roads", "wild-life", "ok/nested"]
    assert "/" not in out["title"] and ":" not in out["title"]
    assert "[[Moose and roads]]" in out["body"] and "[[Made up" not in out["body"] and "a made up note" in out["body"]
    assert "[[Fence study 2019#Results]]" in out["body"]
    assert out["links"] == ["Moose and roads", "Fence study 2019"]
    assert len(out["why"]) <= 200
    good = organize.check({"title": "Fence idea", "folder": "sources", "type": "claim", "tags": [], "body": ""}, ctx, "said")
    assert good["folder"] == "Sources" and good["type"] == "claim" and good["body"] == "said"


def test_organize_fences_note_text_and_writes_nothing(SV, monkeypatch):
    from airag.notes import organize, store
    s, v = SV
    seen = {}

    async def fake(llm, system, user, max_tokens=0):
        seen["system"], seen["user"] = system, user
        return {"title": "Fence walk", "folder": "Notes", "type": "claim", "tags": ["roads"], "body": "Moose by the [[Moose and roads]] fence."}
    monkeypatch.setattr(organize, "complete_json", fake)
    monkeypatch.setattr(organize, "get_llm", lambda settings, task=None: (task, None)[1])
    before = {i["path"] for i in store.tree(s, v)}
    out = asyncio.run(organize.organize(s, v, "um so I saw a moose by the fence"))
    assert out["folder"] == "Notes" and out["links"] == ["Moose and roads"]
    assert "Moose and roads" in seen["user"] and "saw a moose" in seen["user"]
    assert {i["path"] for i in store.tree(s, v)} == before        # only a proposal


def test_notes_task_is_registered():
    from airag.llm import tasks
    assert "notes" in tasks.TASKS
