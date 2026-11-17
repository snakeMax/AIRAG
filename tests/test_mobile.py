"""Android fallbacks and the PC link."""
import asyncio
import socket
import threading
import time

import httpx

from airag import config


def test_ddg_html_parse():
    from airag.search.ddg_html import parse
    html = """<div class="result results_links"><a class="result__a"
      href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.org%2Fpage&rut=x">Example page</a>
      <a class="result__snippet">A short snippet</a></div>
      <div class="result result--ad"><a class="result__a" href="https://ads.example">Ad</a></div>"""
    r = parse(html, 5)
    assert len(r) == 1 and r[0].url == "https://example.org/page" and r[0].snippet == "A short snippet"


def test_library_without_fts(tmp_path):
    from airag.library import Library
    (tmp_path / "notes.md").write_text("Hummingbirds beat their wings about fifty times per second.", encoding="utf-8")
    import sqlite3
    db = tmp_path / "lib.db"
    c = sqlite3.connect(db)   # a plain table, as on SQLite builds without FTS5
    c.execute("CREATE TABLE chunks(text TEXT, title TEXT, file_id INTEGER, ord INTEGER)")
    c.commit(); c.close()
    lib = Library(db)
    lib.sync([str(tmp_path)], [".md"], 5)
    hits = lib.search(["hummingbirds wings"], 5)
    assert lib.fts is False
    assert hits and "fifty" in hits[0]["excerpt"]


def _free():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def test_pclink_needs_code_and_only_proxies_models():
    import uvicorn
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Route
    from airag import pclink
    from airag.llm import get_llm

    async def models(_):
        return JSONResponse({"data": [{"id": "qwen3:8b"}]})
    port = _free()
    fake = uvicorn.Server(uvicorn.Config(Starlette(routes=[Route("/v1/models", models)]), port=port, log_level="error"))
    threading.Thread(target=fake.run, daemon=True).start()
    while not fake.started:
        time.sleep(0.02)
    config.save({"llm": {"providers": {"ollama": {"base_url": f"http://127.0.0.1:{port}"}}}})
    st = pclink.start()
    try:
        assert st["running"] and st["code"]
        s = config.load()
        s["llm"]["provider"] = "pc_link"
        s["llm"]["providers"]["pc_link"] = {"base_url": f"127.0.0.1:{st['port']}", "api_key": st["code"], "model": "x"}
        assert asyncio.run(get_llm(s).list_models()) == ["qwen3:8b"]
        url = f"http://127.0.0.1:{st['port']}"
        assert httpx.get(url + "/v1/models").status_code == 401
        assert httpx.get(url + "/v1/models", headers={"Authorization": "Bearer WRONG"}).status_code == 401
        r = httpx.get(url + "/api/settings", headers={"Authorization": "Bearer " + st["code"]})
        assert r.status_code == 404
    finally:
        pclink.stop(save=True)
        fake.should_exit = True


def test_log_hides_secrets(tmp_path):
    from fastapi.testclient import TestClient
    from airag import paths
    from airag.main import app
    config.save({"llm": {"providers": {"openai": {"api_key": "zz-secret-value-123456"}}}})
    paths.ensure_dirs()
    (paths.LOG_DIR / "airag.log").write_text("x INFO a: key zz-secret-value-123456 and sk-ant-abcdefghijk\n", encoding="utf-8")
    client = TestClient(app, base_url="http://127.0.0.1")
    assert client.get("/api/app/log").status_code == 401       # no session yet
    client.get("/")                                             # the page sets the session cookie
    assert client.get("/api/app/log", headers={"sec-fetch-site": "cross-site"}).status_code == 403
    lines = client.get("/api/app/log").json()["lines"]
    assert lines and "zz-secret" not in lines[-1] and "sk-ant-abc" not in lines[-1]
