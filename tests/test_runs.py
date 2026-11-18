"""Searches keep running when nobody is watching, queue up, and can be cancelled."""
import asyncio

from airag import runs


def test_queue_follow_and_cancel():
    async def scenario():
        runs.RUNS.clear()
        runs._order.clear()
        gate = asyncio.Event()

        async def slow(emit):
            await emit({"type": "step", "id": "a"})
            await gate.wait()
            await emit({"type": "done", "id": "r1"})

        async def quick(emit):
            await emit({"type": "done", "id": "r2"})

        async def never(emit):
            await asyncio.sleep(60)

        r1 = runs.start("r1", "first", "auto", slow)
        r2 = runs.start("r2", "second", "auto", quick)
        r3 = runs.start("r3", "third", "auto", never)
        await asyncio.sleep(0.05)
        assert r1.status == "running" and r2.status == "queued" and r3.status == "queued"
        assert [a["id"] for a in runs.active()] == ["r1", "r2", "r3"]

        # a page that comes back later gets everything so far, then live events
        got = []

        async def watch():
            async for ev in runs.follow(r1):
                got.append(ev["type"])
        w = asyncio.create_task(watch())
        await asyncio.sleep(0.05)
        assert runs.cancel("r3") and r3.status == "cancelled"     # cancelled while queued
        gate.set()
        await asyncio.wait_for(w, 2)
        assert got == ["accepted", "step", "done"]
        await asyncio.sleep(0.05)
        assert r1.status == "done" and r2.status == "done"         # the queued one ran afterwards
        assert runs.active() == []

        r4 = runs.start("r4", "fourth", "auto", never)
        await asyncio.sleep(0.05)
        assert runs.cancel("r4")
        await asyncio.sleep(0.05)
        assert r4.status == "cancelled" and r4.events[-1]["type"] == "cancelled"
    asyncio.run(scenario())


def test_cancel_queued_reaches_listener():
    async def go():
        gate = asyncio.Event()
        async def slow(emit):
            await gate.wait()
        runs.start("q1", "a", "auto", slow)
        r2 = runs.start("q2", "b", "auto", slow)
        got = []
        async def watch():
            async for ev in runs.follow(r2):
                got.append(ev)
        t = asyncio.create_task(watch())
        await asyncio.sleep(0.05)
        assert runs.cancel("q2")
        await asyncio.wait_for(t, 2)
        gate.set()
        await asyncio.sleep(0.05)
        return got
    got = asyncio.run(go())
    assert got[-1]["type"] == "cancelled"
