"""HTTP API + static web UI.

Endpoints are grouped by feature; each feature lives in its own module
(ollama_manager, browser_install, updater, library, summarize, ...), so adding
a feature = new module + a few routes here + UI in web/js/.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import subprocess
import sys
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import (__repo__, __version__, appctl, browser_install, config, history, jobs, languages,
               ollama_manager, paths, updater)
from .fetch import shutdown as fetch_shutdown
from .library import LIBRARY, settings_args as library_args
from .llm import PROVIDERS, LLMError, get_llm
from . import prompts as prompts_mod
from .pipeline import Research
from .search import BACKENDS, get_search
from .summarize import summarize

log = logging.getLogger("airag")
WEB = paths.WEB_DIR

app = FastAPI(title="AIRAG", version=__version__, docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=WEB), name="static")
LOOPBACK = {"127.0.0.1", "localhost", "::1", "[::1]"}
app.state.loopback_only = True


# A random token for this run. The page gets it as a same-site cookie when it loads,
# and every API call must carry it, so other websites open in the browser can't use the API.
SESSION_TOKEN = secrets.token_urlsafe(24)
SESSION_COOKIE = "airag_session"
OPEN_PATHS = {"/", "/api/app/ping", "/api/app/show", "/favicon.ico"}


@app.middleware("http")
async def only_local(request: Request, call_next):
    """Block DNS rebinding (Host check) and requests from other sites (session cookie + Sec-Fetch-Site)."""
    if app.state.loopback_only:
        host = (request.headers.get("host") or "").rsplit(":", 1)[0].strip("[]").lower()
        if host and host not in LOOPBACK and host != "::1":
            return JSONResponse({"detail": "Forbidden host"}, status_code=403)
    path = request.url.path
    if path.startswith("/api/") and path not in OPEN_PATHS:
        if request.headers.get("sec-fetch-site") == "cross-site":
            return JSONResponse({"detail": "Cross-site request blocked"}, status_code=403)
        given = request.cookies.get(SESSION_COOKIE) or request.headers.get("x-airag-token") or ""
        if not secrets.compare_digest(given.encode(), SESSION_TOKEN.encode()):
            return JSONResponse({"detail": "Reload AIRAG to continue (session expired)."}, status_code=401)
    return await call_next(request)


@app.on_event("startup")
async def _startup() -> None:
    s = config.load()
    if s["llm"]["provider"] == "ollama" and s["llm"]["providers"]["ollama"].get("autostart", False):
        asyncio.create_task(ollama_manager.ensure_running(s["llm"]["providers"]["ollama"].get("base_url") or ollama_manager.DEFAULT_URL))
    if s["app"].get("check_updates", True):
        asyncio.create_task(updater.check())
    if not paths.ANDROID and s["app"].get("pclink_enabled"):
        from . import pclink
        await asyncio.to_thread(pclink.autostart)


@app.on_event("shutdown")
async def _shutdown() -> None:
    await fetch_shutdown()
    if not paths.ANDROID:
        from . import pclink
        pclink.stop()


@app.get("/")
def index():
    r = FileResponse(WEB / "index.html", headers={"Cache-Control": "no-cache"})
    r.set_cookie(SESSION_COOKIE, SESSION_TOKEN, httponly=True, samesite="strict", path="/")
    return r


def _err(e: Exception, code: int = 400) -> HTTPException:
    return HTTPException(code, str(e) or type(e).__name__)


# app / window
@app.get("/api/app/ping")
def ping():
    return {"app": "airag", "pid": os.getpid(), "version": __version__}


@app.get("/api/app/info")
def app_info():
    return {"version": __version__, "repo": __repo__, "mode": appctl.mode, "frozen": paths.FROZEN,
            "portable": paths.is_portable(), "platform": paths.PLATFORM, "port": appctl.port, "can_self_update": updater.can_self_update(),
            "config_dir": str(paths.CONFIG_DIR), "local_dir": str(paths.LOCAL_DIR),
            "languages": languages.public_list(), "can_restart": appctl.mode in ("desktop", "browser")}


@app.post("/api/app/show")
def app_show():
    appctl.show()
    return {"ok": True}


class RestartReq(BaseModel):
    mode: Optional[str] = None


@app.post("/api/app/restart")
def app_restart(req: RestartReq):
    if req.mode in ("desktop", "browser"):
        config.save({"app": {"ui_mode": req.mode}})
    if appctl.mode == "server":
        return {"ok": False, "message": "Restart AIRAG manually to apply."}
    appctl.restart(req.mode)
    return {"ok": True}


@app.post("/api/app/quit")
def app_quit():
    appctl.quit_app()
    return {"ok": True}


@app.get("/api/app/storage")
def storage():
    return {"history": paths.dir_size(paths.HISTORY_DIR), "history_count": len(list(paths.HISTORY_DIR.glob("*.json")))
            if paths.HISTORY_DIR.exists() else 0, "library": LIBRARY.stats().get("bytes", 0),
            "browser": paths.dir_size(paths.BROWSERS_DIR) if paths.BROWSERS_DIR.exists() else 0,
            "logs": paths.dir_size(paths.LOG_DIR), "updates": paths.dir_size(paths.UPDATES_DIR)}


class OpenReq(BaseModel):
    target: str  # config | local | logs


@app.post("/api/app/open-folder")
def open_folder(req: OpenReq):
    p = {"config": paths.CONFIG_DIR, "local": paths.LOCAL_DIR, "logs": paths.LOG_DIR}.get(req.target)
    if not p:
        raise HTTPException(400, "unknown folder")
    p.mkdir(parents=True, exist_ok=True)
    _open_path(p)
    return {"ok": True}


def _open_path(p: Path, reveal: bool = False) -> None:
    if paths.ANDROID:
        from .android_bridge import open_path
        open_path(str(p), reveal)
    elif sys.platform == "win32":
        if reveal:
            subprocess.Popen(["explorer", "/select,", str(p)])
        else:
            os.startfile(str(p))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", str(p)] if reveal else ["open", str(p)])
    else:
        subprocess.Popen(["xdg-open", str(p.parent if reveal else p)])


# settings
@app.get("/api/schema")
def schema():
    return {
        "llm": {"providers": [{"name": n, "label": c.label, "fields": c.fields} for n, c in PROVIDERS.items()],
                "fields": config.GENERAL_SCHEMA["llm"]},
        "search": {"backends": [{"name": n, "label": c.label, "fields": c.fields, "supports_images": c.supports_images}
                                for n, c in BACKENDS.items()],
                   "fields": config.GENERAL_SCHEMA["search"]},
        "app": config.GENERAL_SCHEMA["app"],
        "fetch": config.GENERAL_SCHEMA["fetch"],
        "research": config.GENERAL_SCHEMA["research"],
        "library": config.GENERAL_SCHEMA["library"],
        "prompts": config.GENERAL_SCHEMA["prompts"],
        "default_article_prompt": prompts_mod.ARTICLE_RULES,
        "languages": languages.public_list(),
        "version": __version__,
    }


@app.get("/api/settings")
def get_settings():
    return config.masked(config.load())


@app.post("/api/settings")
def save_settings(body: dict):
    return config.masked(config.save(body))


def _needs_key(s: dict) -> bool:
    name = s["llm"]["provider"]
    cls = PROVIDERS.get(name)
    if not cls:
        return True
    secret = [f for f in cls.fields if f.get("type") == "secret"]
    required = getattr(cls, "requires_key", any(f["key"] == "api_key" for f in secret) and name != "openai_compatible")
    return bool(required) and not s["llm"]["providers"].get(name, {}).get("api_key")


@app.get("/api/status")
async def status():
    s = config.load()
    try:
        llm = get_llm(s).describe()
    except Exception as e:
        llm = f"not configured ({e})"
    try:
        search = get_search(s).label
    except Exception as e:
        search = str(e)
    out = {"llm": llm, "provider": s["llm"]["provider"], "search": search, "version": __version__,
           "needs_key": _needs_key(s), "setup_done": bool(s["app"].get("setup_done")), "ollama": None,
           "library_folders": len(library_args(s)["folders"]), "browser_ready": browser_install.installed()}
    if s["llm"]["provider"] == "ollama":
        url = s["llm"]["providers"]["ollama"].get("base_url") or ollama_manager.DEFAULT_URL
        st = await ollama_manager.status(url)
        model = s["llm"]["providers"]["ollama"].get("model")
        out["ollama"] = {"running": st["running"], "installed": st["installed"],
                         "model_present": any(m["name"] == model or m["name"] == f"{model}:latest" for m in st["models"])}
    return out


class ProviderReq(BaseModel):
    provider: str
    config: Optional[dict] = None
    temperature: Optional[float] = None


@app.post("/api/models")
async def models(req: ProviderReq):
    s = config.with_overrides(config.load(), req.provider, req.config or {})
    try:
        return {"models": await get_llm(s).list_models()}
    except LLMError as e:
        raise _err(e)
    except Exception as e:
        raise HTTPException(400, f"Couldn't list models: {e}")


@app.post("/api/test-llm")
async def test_llm(req: ProviderReq):
    s = config.with_overrides(config.load(), req.provider, req.config or {})
    if req.temperature is not None:
        s["llm"]["temperature"] = req.temperature
    try:
        llm = get_llm(s)
        reply = await llm.complete("You are a connection test.", "Reply with exactly: OK", max_tokens=200)
        return {"ok": True, "reply": reply.strip()[:200], "model": llm.describe()}
    except LLMError as e:
        raise _err(e)
    except Exception as e:
        raise HTTPException(400, f"{type(e).__name__}: {e}")


# jobs
@app.get("/api/jobs/{job_id}")
def job_get(job_id: str):
    j = jobs.JOBS.get(job_id)
    if not j:
        raise HTTPException(404, "No such job")
    return j.public()


@app.get("/api/jobs")
def job_list(key: str = ""):
    return {"items": [j.public() for j in jobs.JOBS.values() if not key or j.key.startswith(key)]}


@app.post("/api/jobs/{job_id}/cancel")
def job_cancel(job_id: str):
    return {"cancelled": jobs.cancel(job_id)}


# log viewer (Settings → About). Secrets are blanked out before the text leaves the server.
@app.get("/api/app/log")
def app_log(lines: int = 300, level: str = ""):
    import re
    f = paths.LOG_DIR / "airag.log"
    if not f.exists():
        return {"lines": [], "path": str(f)}
    with open(f, "rb") as fh:
        fh.seek(0, 2)
        size = fh.tell()
        fh.seek(max(0, size - 400_000))
        text = fh.read().decode("utf-8", errors="replace")
    rows = text.splitlines()[-max(10, min(lines, 2000)) * 3:]
    if level:
        lv = level.upper()
        keep = {"ERROR": ("ERROR", "CRITICAL"), "WARNING": ("WARNING", "ERROR", "CRITICAL")}.get(lv)
        if keep:
            rows = [r for r in rows if any(f" {k} " in r for k in keep) or r.startswith((" ", "\t", "Traceback"))]
    rows = rows[-min(lines, 2000):]
    secrets_ = [v for v in _secret_values() if len(v) >= 8]
    key_re = re.compile(r"(sk-[A-Za-z0-9_\-]{8,}|sk-ant-[A-Za-z0-9_\-]{8,}|AIza[0-9A-Za-z_\-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|Bearer\s+\S+)")
    out = []
    for r in rows:
        for v in secrets_:
            r = r.replace(v, "••••")
        out.append(key_re.sub("••••", r))
    return {"lines": out, "path": str(f)}


def _secret_values() -> list:
    s = config.load()
    vals = [s["app"].get("pclink_code") or ""]
    for prov in s["llm"].get("providers", {}).values():
        vals += [str(v) for k, v in prov.items() if "key" in k and v]
    for sec in ("search",):
        vals += [str(v) for k, v in _walk(s.get(sec, {})) if "key" in k and v]
    return vals


def _walk(d, prefix=""):
    for k, v in d.items():
        if isinstance(v, dict):
            yield from _walk(v, k)
        else:
            yield k, v


# ollama
def _ollama_url(override: Optional[str] = None) -> str:
    return override or config.load()["llm"]["providers"]["ollama"].get("base_url") or ollama_manager.DEFAULT_URL


@app.get("/api/ollama/status")
async def ollama_status(url: str = ""):
    return await ollama_manager.status(_ollama_url(url))


@app.post("/api/ollama/start")
async def ollama_start(url: str = ""):
    ok = await ollama_manager.ensure_running(_ollama_url(url))
    st = await ollama_manager.status(_ollama_url(url))
    if not ok:
        st["error"] = "Ollama isn't installed." if not st["installed"] else "Ollama didn't start in time."
    return st


# PC link (share this PC's Ollama with the phone app)
class PcLinkReq(BaseModel):
    enabled: Optional[bool] = None
    allow_internet: Optional[bool] = None
    new_code: bool = False


@app.get("/api/pclink")
def pclink_status():
    from . import pclink
    return pclink.status()


@app.post("/api/pclink")
def pclink_set(req: PcLinkReq):
    from . import pclink
    if paths.ANDROID:
        raise HTTPException(400, "PC link is set up in the desktop app.")
    if req.allow_internet is not None:
        config.save({"app": {"pclink_allow_internet": bool(req.allow_internet)}})
    if req.new_code:
        config.save({"app": {"pclink_code": pclink.new_code()}})
    try:
        if req.enabled is False:
            pclink.stop(save=True)
        elif req.enabled or ((req.allow_internet is not None or req.new_code) and pclink.running()):
            pclink.start()
    except Exception as e:
        raise _err(e)
    return pclink.status()


@app.get("/api/ollama/recommended")
def ollama_recommended():
    return ollama_manager.recommended()


class ModelReq(BaseModel):
    model: str
    url: Optional[str] = None


@app.post("/api/ollama/pull")
async def ollama_pull(req: ModelReq):
    url = _ollama_url(req.url)
    if not await ollama_manager.ensure_running(url):
        raise HTTPException(400, "Ollama isn't running and couldn't be started. Install it from ollama.com/download.")
    job = jobs.start(f"ollama-pull:{req.model}", lambda j: ollama_manager.pull(url, req.model.strip(), j))
    return job.public()


@app.post("/api/ollama/delete")
async def ollama_delete(req: ModelReq):
    try:
        await ollama_manager.delete(_ollama_url(req.url), req.model)
    except Exception as e:
        raise _err(e)
    return {"ok": True}


# headless browser
@app.get("/api/browser/status")
def browser_status():
    return browser_install.status()


@app.post("/api/browser/install")
async def browser_install_start():
    return jobs.start_thread("browser-install", browser_install.install).public()


@app.post("/api/browser/uninstall")
async def browser_uninstall():
    await fetch_shutdown()
    return browser_install.uninstall()


# updates
@app.get("/api/update/check")
async def update_check(force: bool = False):
    return await updater.check(force=force)


@app.post("/api/update/install")
async def update_install():
    return jobs.start("update", lambda j: updater.download_and_install(j, appctl.quit_app)).public()


# check & repair
@app.get("/api/repair/check")
async def repair_check():
    from . import repair
    r = await asyncio.to_thread(repair.check)
    r["can_reinstall"] = updater.can_self_update()
    return r


@app.post("/api/repair")
async def repair_run():
    from . import repair
    return jobs.start("repair", lambda j: repair.repair(j, appctl.quit_app)).public()


@app.post("/api/repair/reinstall")
async def repair_reinstall():
    return jobs.start("update", lambda j: updater.download_and_install(j, appctl.quit_app, reinstall=True)).public()


def _reindex_soon() -> None:
    """Index new files in the library folders in the background (only changed files are read)."""
    if jobs.running("library-sync"):
        return
    asyncio.get_running_loop().run_in_executor(None, lambda: LIBRARY.sync(**library_args(config.load())))


# My library: personal folder for saved articles and imported files
@app.get("/api/mylibrary")
def mylibrary_status():
    from . import mylibrary
    return mylibrary.status(config.load())


class MyFolderReq(BaseModel):
    path: Optional[str] = None     # None = open the folder picker; "" = back to the default location


@app.post("/api/mylibrary/folder")
async def mylibrary_folder(req: MyFolderReq):
    from . import mylibrary
    path = req.path
    if path is None:
        try:
            path = await asyncio.to_thread(appctl.pick_folder)
        except RuntimeError as e:
            raise _err(e)
        if not path:
            return mylibrary.status(config.load())
    if path:
        p = Path(path.strip().strip('"')).expanduser()
        try:
            p.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise HTTPException(400, f"Can't use that folder: {e}")
        path = str(p)
    s = config.save({"library": {"personal_folder": path}})
    return mylibrary.status(s)


class SaveReq(BaseModel):
    id: str
    rich: bool = False      # also keep pictures and the interactive explainer


@app.post("/api/mylibrary/save")
async def mylibrary_save(req: SaveReq):
    from . import mylibrary
    rec = history.get(req.id)
    if not rec:
        raise HTTPException(404, "Search not found")
    s = config.load()
    try:
        path = await asyncio.to_thread(mylibrary.save_article, rec, s, req.rich)
    except (ValueError, OSError) as e:
        raise _err(e)
    rec["saved_path"] = str(path)
    history.save(rec, int(s["app"].get("history_limit", 300)))
    _reindex_soon()
    return {"path": str(path)}


@app.get("/api/mylibrary/saved")
def mylibrary_saved():
    from . import mylibrary
    return {"items": mylibrary.list_saved(config.load())}


@app.get("/api/mylibrary/saved/{name}")
def mylibrary_saved_one(name: str):
    from . import mylibrary
    try:
        return mylibrary.load_saved(config.load(), name)
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(404, str(e))


class SaveSourceReq(BaseModel):
    url: str
    query: str = ""


@app.post("/api/mylibrary/save-source")
async def mylibrary_save_source(req: SaveSourceReq):
    from . import mylibrary
    from .fetch import fetch_page
    if not req.url.startswith(("http://", "https://")):
        raise HTTPException(400, "Only web pages can be saved this way.")
    s = config.load()
    page = await fetch_page(req.url, s["fetch"])
    if not page.ok or not page.text.strip():
        raise HTTPException(400, f"Couldn't read the page: {page.error or 'no text'}")
    try:
        path = await asyncio.to_thread(mylibrary.save_source, page, s, req.query)
    except OSError as e:
        raise _err(e)
    _reindex_soon()
    return {"path": str(path)}


class ImportReq(BaseModel):
    move: bool = False


@app.post("/api/mylibrary/import")
async def mylibrary_import(req: ImportReq):
    from . import mylibrary
    s = config.load()
    dest = mylibrary.ensure(s)
    if paths.ANDROID:
        from . import android_bridge
        added = await asyncio.to_thread(android_bridge.import_files, str(dest), req.move)
        _reindex_soon()
        return {"added": [a["path"] for a in added], "moved": sum(1 for a in added if a.get("moved"))}
    files = await asyncio.to_thread(appctl.pick_files)
    try:
        added = await asyncio.to_thread(mylibrary.import_files, files, s, req.move)
    except OSError as e:
        raise _err(e)
    _reindex_soon()
    return {"added": added, "moved": len(added) if req.move else 0}


@app.post("/api/mylibrary/open")
def mylibrary_open():
    from . import mylibrary
    _open_path(mylibrary.ensure(config.load()), reveal=False)
    return {"ok": True}


# library (Retrieve & Get)
@app.get("/api/library/status")
def library_status():
    s = config.load()
    folders = []
    for f in s["library"].get("folders") or []:
        folders.append({"path": f, "exists": Path(f).expanduser().is_dir()})
    running = jobs.running("library-sync")
    return {"folders": folders, "stats": LIBRARY.stats(), "job": running.public() if running else None}


@app.post("/api/library/pick-folder")
async def library_pick():
    try:
        path = await asyncio.to_thread(appctl.pick_folder)
    except RuntimeError as e:
        raise _err(e)
    return {"path": path}


class FolderReq(BaseModel):
    path: str


@app.post("/api/library/folders/add")
def library_add(req: FolderReq):
    p = Path(req.path.strip().strip('"')).expanduser()
    if not p.is_dir():
        raise HTTPException(400, f"Folder not found: {p}")
    s = config.load()
    folders = list(s["library"].get("folders") or [])
    if str(p) not in folders:
        folders.append(str(p))
    config.save({"library": {"folders": folders}})
    return library_status()


@app.post("/api/library/folders/remove")
def library_remove(req: FolderReq):
    s = config.load()
    folders = [f for f in (s["library"].get("folders") or []) if f != req.path]
    config.save({"library": {"folders": folders}})
    return library_status()


def _sync_job(job):
    s = config.load()

    def progress(i, n, path):
        job.progress = (i / n) if n else None
        job.detail = Path(path).name
        job.message = f"Indexing {i + 1} of {n} changed files"
    job.message = "Scanning folders"
    return LIBRARY.sync(progress=progress, cancelled=lambda: job.cancelled, **library_args(s))


@app.post("/api/library/sync")
async def library_sync():
    return jobs.start_thread("library-sync", _sync_job).public()


@app.post("/api/library/clear")
def library_clear():
    LIBRARY.clear()
    return library_status()


def _library_file(fid: int) -> Path:
    f = LIBRARY.get_file(fid)
    if not f:
        raise HTTPException(404, "File not in library")
    from .library import allowed_file
    if not allowed_file(f["path"], config.load()):
        raise HTTPException(404, "File no longer available")
    return Path(f["path"]).resolve()


@app.get("/api/library/file/{fid}")
def library_file(fid: int):
    p = _library_file(fid)
    text_types = {".md", ".markdown", ".txt", ".text", ".rst", ".org", ".tex", ".csv", ".json", ".log"}
    if p.suffix.lower() in text_types:
        return FileResponse(p, media_type="text/plain; charset=utf-8")
    return FileResponse(p, filename=p.name, content_disposition_type="inline")


class OpenFileReq(BaseModel):
    file_id: int
    reveal: bool = False


@app.post("/api/library/open")
def library_open(req: OpenFileReq):
    _open_path(_library_file(req.file_id), req.reveal)
    return {"ok": True}


# research + summaries
def _ndjson(gen_factory):
    queue: asyncio.Queue = asyncio.Queue()

    async def emit(ev: dict) -> None:
        await queue.put(ev)

    async def runner() -> None:
        try:
            await gen_factory(emit)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.exception("stream failed")
            await queue.put({"type": "error", "message": str(e) or type(e).__name__})
        finally:
            await queue.put(None)

    task = asyncio.create_task(runner())

    async def stream():
        try:
            while True:
                ev = await queue.get()
                if ev is None:
                    break
                yield json.dumps(ev, ensure_ascii=False) + "\n"
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(stream(), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


class ResearchReq(BaseModel):
    query: str
    mode: str = "auto"
    include_library: bool = False
    ui_lang: Optional[str] = None
    from_id: Optional[str] = None     # reuse the sources of this earlier search
    date_from: str = ""               # only results from this period (YYYY-MM-DD, either may be empty)
    date_to: str = ""
    merge_id: Optional[str] = None    # search again, also using the sources of this earlier search


@app.post("/api/research")
async def research(req: ResearchReq):
    settings = config.load()
    prompts_mod.use(settings)
    return _ndjson(lambda emit: Research(req.query, req.mode, settings, emit, req.include_library, req.ui_lang,
                                                    req.from_id, req.date_from, req.date_to, req.merge_id).run())


class TranslateReq(BaseModel):
    lang: str
    markdown: str = ""
    id: Optional[str] = None
    items: list = []


@app.post("/api/translate/article")
async def translate_article(req: TranslateReq):
    from . import translate
    settings = config.load()

    async def run(emit):
        async for piece in translate.article(settings, req.markdown, req.lang, req.id):
            await emit({"type": "token", "text": piece})
        await emit({"type": "done"})
    return _ndjson(run)


@app.post("/api/translate/items")
async def translate_items(req: TranslateReq):
    from . import translate
    try:
        return {"items": await translate.items(config.load(), req.items, req.lang)}
    except Exception as e:
        raise _err(e)


class SummaryReq(BaseModel):
    kind: str          # article | results | source | text
    query: str = ""
    payload: dict = {}
    ui_lang: Optional[str] = None


@app.post("/api/summarize")
async def summarize_route(req: SummaryReq):
    settings = config.load()
    prompts_mod.use(settings)

    async def run(emit):
        async for piece in summarize(settings, req.kind, req.query, req.payload, req.ui_lang):
            await emit({"type": "token", "text": piece})
        await emit({"type": "done"})
    return _ndjson(run)


class InteractiveReq(BaseModel):
    id: str
    force: bool = False
    ui_lang: Optional[str] = None


@app.post("/api/interactive")
async def interactive_route(req: InteractiveReq):
    from .interactive import generate
    settings = config.load()
    prompts_mod.use(settings)
    try:
        return await generate(settings, req.id, req.ui_lang, req.force)
    except (ValueError, LLMError) as e:
        raise _err(e)


# history
@app.get("/api/history")
def history_list():
    return {"items": history.listing()}


@app.get("/api/history/{rid}")
def history_get(rid: str):
    r = history.get(rid)
    if r is None:
        raise HTTPException(404, "Not found")
    return r


@app.delete("/api/history/{rid}")
def history_delete(rid: str):
    return {"deleted": history.delete(rid)}


@app.delete("/api/history")
def history_clear():
    return {"deleted": history.clear()}
