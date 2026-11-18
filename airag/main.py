"""HTTP API + static web UI.

Endpoints are grouped by feature; each feature lives in its own module
(ollama_manager, browser_install, updater, library, summarize, ...), so adding
a feature = new module + a few routes here + UI in web/js/.
"""
from __future__ import annotations

import asyncio
import json
import re
import logging
import os
import secrets
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import (__repo__, __version__, appctl, browser_install, config, guard, history, jobs, languages,
               ollama_manager, paths, runs, updater)
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
OPEN_PATHS = {"/", "/api/app/ping", "/api/app/show", "/api/app/open-path", "/favicon.ico"}


@app.middleware("http")
async def only_local(request: Request, call_next):
    """Block DNS rebinding (Host check) and requests from other sites (session cookie + Sec-Fetch-Site)."""
    if app.state.loopback_only:
        host = (request.headers.get("host") or "").rsplit(":", 1)[0].strip("[]").lower()
        if host and host not in LOOPBACK and host != "::1":
            return JSONResponse({"detail": "Forbidden host"}, status_code=403)
    path = request.url.path
    if path.startswith("/static/"):
        # always check for a newer copy, so an app update never runs with the previous version's scripts
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-cache"
        return response
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
    from . import usage
    asyncio.create_task(usage.refresh_prices())     # model prices for the cost tracker, at most daily
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
    from . import build_info
    return {"version": __version__, "build": build_info(), "repo": __repo__, "mode": appctl.mode, "frozen": paths.FROZEN,
            "portable": paths.is_portable(), "platform": paths.PLATFORM, "port": appctl.port, "can_self_update": updater.can_self_update(),
            "config_dir": str(paths.CONFIG_DIR), "local_dir": str(paths.LOCAL_DIR),
            "languages": languages.public_list(), "can_restart": appctl.mode in ("desktop", "browser")}


@app.post("/api/app/show")
def app_show():
    appctl.show()
    return {"ok": True}


class OpenPathReq(BaseModel):
    path: str


@app.post("/api/app/open-path")
def app_open_path(req: OpenPathReq, request: Request):
    """Open with AIRAG while AIRAG is already running. Only AIRAG's own launcher knows the key (it's in the
    private runtime file), so other programs and websites can't make AIRAG read files."""
    given = request.headers.get("x-airag-launch") or ""
    if not secrets.compare_digest(given.encode(), appctl.launch_key.encode()):
        raise HTTPException(403, "Not allowed")
    from . import openfile, mylibrary
    try:
        name, data = openfile.read_path(req.path)
        lib = mylibrary.folder(config.load()).resolve()
        trusted = lib in Path(req.path).resolve().parents
        openfile.queue(openfile.open_file(name, trusted=trusted, data=data)["id"])
    except Exception as e:
        openfile.errors.append(str(e))
    appctl.show()
    return {"ok": True}


@app.get("/api/app/inbox")
def app_inbox():
    """A file handed over by the operating system (Open with AIRAG), for the page to show."""
    from . import openfile
    return openfile.take()


class OpenFileBody(BaseModel):
    name: str
    text: str = ""
    data: str = ""          # the file's bytes, base64 (anything that isn't plain text)


@app.post("/api/open-file")
async def open_file(req: OpenFileBody):
    """A file the reader picked in AIRAG (or shared to it on Android). Opened without the AI."""
    from . import openfile
    import base64
    try:
        data = None
        if req.data:
            if len(req.data) > openfile.MAX_BYTES * 4 // 3 + 8:
                raise openfile.NotOpenable("The file is too big to open (over 20 MB).")
            try:
                data = base64.b64decode(req.data, validate=True)
            except ValueError:
                raise HTTPException(400, "The file couldn't be read.")
        rec = await asyncio.to_thread(openfile.open_file, req.name, req.text, False, data)
    except openfile.NotOpenable as e:
        raise HTTPException(400, str(e))
    return {"id": rec["id"]}


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
        "defaults": config.GENERAL_SCHEMA["defaults"],
        "usage": config.GENERAL_SCHEMA["usage"],
        "buttons": config.GENERAL_SCHEMA["buttons"],
        "default_article_prompt": prompts_mod.ARTICLE_RULES,
        "languages": languages.public_list(),
        "version": __version__,
    }


@app.get("/api/settings")
def get_settings():
    return config.masked(config.load())


def _busy_guard(what: str) -> None:
    """Guarded execution: things that would disturb a running task (clearing caches, the library index or
    History) wait until running tasks have finished or been cancelled."""
    if config.guarded() and runs.active():
        raise HTTPException(409, f"{what} would disturb the task that is running, so it waits. Try again when it has "
                                 "finished, or cancel it first. (Settings → System → Guarded execution)")


@app.post("/api/settings")
def save_settings(body: dict):
    before = config.load() if runs.active() else None
    out = config.masked(config.save(body))
    if before is not None:
        later = config.changed_for_running(before, config.load())
        if later:
            out["_applies_later"] = later       # the running task keeps its settings; these apply to the next one
    return out


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
    vision = False
    try:
        engine = get_llm(s)
        llm = engine.describe()
        vision = bool(getattr(engine, "supports_vision", False))
    except Exception as e:
        llm = f"not configured ({e})"
    try:
        search = get_search(s).label
    except Exception as e:
        search = str(e)
    out = {"llm": llm, "provider": s["llm"]["provider"], "search": search, "version": __version__,
           "needs_key": _needs_key(s), "setup_done": bool(s["app"].get("setup_done")), "ollama": None,
           "library_folders": len(library_args(s)["folders"]), "browser_ready": browser_install.installed(), "vision": vision}
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


@app.get("/api/system")
def system_info(refresh: bool = False):
    from . import hardware
    return hardware.info(refresh)


# backup: export / import settings and history
class ExportReq(BaseModel):
    include_keys: bool = False


@app.post("/api/backup/export")
def backup_export(req: ExportReq):
    from . import backup, mylibrary
    try:
        path = backup.export(mylibrary.ensure(config.load()) / "Backups", req.include_keys)
    except OSError as e:
        raise _err(e)
    return {"path": str(path)}


@app.post("/api/backup/import")
async def backup_import():
    from . import backup
    if paths.ANDROID:
        from . import android_bridge
        tmp = paths.LOCAL_DIR / "import"
        picked = await asyncio.to_thread(android_bridge.import_files, str(tmp), False)
        files = [p["path"] for p in picked]
    else:
        files = await asyncio.to_thread(appctl.pick_files)
    if not files:
        return {"imported": False}
    try:
        result = await asyncio.to_thread(backup.import_file, Path(files[0]))
    except ValueError as e:
        raise _err(e)
    finally:
        if paths.ANDROID:
            for f in files:
                Path(f).unlink(missing_ok=True)
    return result


# clear caches (Settings): pages read during searches, the update check, and (on Android) the WebView cache
@app.post("/api/app/clear-cache")
def clear_cache():
    _busy_guard("Clearing the cache")
    from . import fetch
    pages = len(fetch._cache)
    fetch._cache.clear()
    fetch._cache_chars = 0
    updater.CACHE.unlink(missing_ok=True)
    if paths.ANDROID:
        from .android_bridge import clear_web_cache
        clear_web_cache()
    return {"pages": pages}


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
    if req.new_code:
        config.save({"app": {"pclink_code": pclink.new_code()}})
    try:
        if req.enabled is False:
            pclink.stop(save=True)
        elif req.enabled or (req.new_code and pclink.running()):
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
    tags: Optional[List[str]] = None            # None = keep the article's tags
    translations: Optional[List[str]] = None    # languages to keep (None = all)


@app.post("/api/mylibrary/save")
async def mylibrary_save(req: SaveReq):
    from . import mylibrary
    rec = history.get(req.id)
    if not rec:
        raise HTTPException(404, "Search not found")
    s = config.load()
    from . import tags as tagmod
    if req.tags is not None:
        rec["tags"] = tagmod.clean(req.tags)
    try:
        path = await asyncio.to_thread(mylibrary.save_article, rec, s, req.rich, req.translations)
    except (ValueError, OSError) as e:
        raise _err(e)
    history.update(req.id, {"saved_path": str(path), **({"tags": rec["tags"]} if req.tags is not None else {})})
    _reindex_soon()
    return {"path": str(path)}


@app.get("/api/offline")
async def offline_state():
    """Offline mode and the local models it could use (nothing is started here)."""
    from . import offline, ollama_manager
    from .llm import PROVIDERS
    s = config.load()
    lib = s["library"]
    choices = offline.local_choices(s)
    for c in choices:
        c["models"] = []
        if c["provider"] == "ollama":
            url = s["llm"]["providers"].get("ollama", {}).get("base_url") or "http://localhost:11434"
            try:
                if await ollama_manager.version(url):      # running already: list what's installed
                    c["models"] = [m["name"] for m in await ollama_manager.list_models(url)]
            except Exception:
                pass
    name = s["llm"].get("provider", "")
    cls = PROVIDERS.get(name)
    model = s["llm"].get("providers", {}).get(name, {}).get("model", "")
    return {"on": bool(lib.get("offline")), "writer": lib.get("offline_writer") or "current",
            "provider": lib.get("offline_provider") or "", "model": lib.get("offline_model") or "",
            "choices": choices, "current": {"provider": name, "label": cls.label if cls else name, "model": model,
                                            "local": any(c["provider"] == name for c in choices)}}


class OfflineReq(BaseModel):
    on: bool
    writer: str = "current"        # "current" or "local"
    provider: str = ""
    model: str = ""


@app.post("/api/offline")
async def offline_set(req: OfflineReq):
    from . import offline, ollama_manager
    s = config.load()
    writer = req.writer if req.writer in ("current", "local") else "current"
    if req.on and writer == "local":
        ok = {c["provider"] for c in offline.local_choices(s)}
        if req.provider not in ok:
            raise HTTPException(400, "That local model isn't set up. Add it in Settings → AI model first.")
    s = config.save({"library": {"offline": bool(req.on), "offline_writer": writer,
                                 "offline_provider": req.provider[:40] if writer == "local" else "",
                                 "offline_model": req.model[:120] if writer == "local" else ""}})
    if req.on and writer == "local" and req.provider == "ollama":     # you chose it: start Ollama now
        url = s["llm"]["providers"].get("ollama", {}).get("base_url") or "http://localhost:11434"
        if ollama_manager.is_local(url):
            asyncio.create_task(ollama_manager.ensure_running(url))
    out = await offline_state()
    out["applies_later"] = bool(config.guarded() and runs.active())     # running tasks finish as they started
    return out


class TagsReq(BaseModel):
    tags: List[str]


@app.post("/api/tags/{rid}")
async def set_tags(rid: str, req: TagsReq):
    """Tags of an article; a saved copy (Markdown properties + AIRAG copy) is updated too."""
    from . import tags as tagmod, mylibrary
    clean = [t for t in tagmod.clean(req.tags) if t != tagmod.DEFAULT]
    rec = history.update(rid, {"tags": clean})
    if not rec:
        raise HTTPException(404, "Search not found")
    if rec.get("saved_path"):
        try:
            await asyncio.to_thread(mylibrary.set_tags, rec, config.load())
            _reindex_soon()
        except OSError:
            pass
    return {"tags": clean}


@app.post("/api/tags/{rid}/suggest")
async def suggest_tags(rid: str):
    """A few tags from the AI (runs as a background job; tokens only when pressed)."""
    from . import tags as tagmod
    rec = history.get(rid)
    if not rec or not rec.get("article"):
        raise HTTPException(404, "Article not found")
    s = config.load()
    return await _job_result(lambda: _suggest(s, rec), "tags", rec.get("title") or rec.get("query") or "", rid)


async def _suggest(s: dict, rec: dict) -> dict:
    from . import tags as tagmod
    return {"tags": await tagmod.suggest(s, rec)}


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
    _busy_guard("Clearing the library index")
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
    extras: bool = True               # pictures + interactive explainer check
    extend_id: Optional[str] = None   # "Locate more sources" for this finished article


@app.post("/api/research")
async def research(req: ResearchReq):
    """Starts a search (or queues it behind a running one) and streams its progress.
    Closing the stream doesn't stop the search: /api/research/{id}/stream picks it up again."""
    from . import runs, usage
    settings = config.load()
    if usage.over_budget(settings):
        raise HTTPException(402, usage.BUDGET_MESSAGE)
    holder: dict = {}

    async def emit(ev: dict) -> None:
        await holder["run"].emit(ev)
    try:
        r = Research(req.query, req.mode, settings, emit, req.include_library, req.ui_lang, req.from_id,
                     req.date_from, req.date_to, req.merge_id, req.extras, req.extend_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if r.extend:
        r.run_id = r.id + "-more"
        if runs.RUNS.get(r.run_id) and not runs.RUNS[r.run_id].finished:
            return _follow(runs.RUNS[r.run_id])     # already looking: just watch that one

    async def go(_emit) -> None:
        prompts_mod.use(settings)    # the task may start later (queued), so set the prompt settings here
        await r.run()
    while not r.extend and r.id in runs.RUNS:          # same question twice in the same second
        r.id += "-2"
        r.run_id = r.id
    try:
        holder["run"] = runs.start(r.run_id, r.query, req.mode, go, kind="more" if r.extend else "search",
                                   ref=r.id if r.extend else "")
    except runs.TooManyJobs as e:
        raise HTTPException(429, str(e))
    return _follow(holder["run"])


class SoundReq(BaseModel):
    data: str
    ext: str


@app.get("/api/sounds/{name}")
def sound_file(name: str, builtin: bool = False):
    from . import sounds
    f = (None if builtin else sounds.custom_file(name)) or sounds.default_file(name)
    if not f:
        raise HTTPException(404, "No such sound")
    return FileResponse(f, media_type=sounds.TYPES.get(f.suffix[1:].lower(), "audio/wav"),
                        headers={"Cache-Control": "no-cache"})


@app.post("/api/sounds/{name}")
def sound_upload(name: str, req: SoundReq):
    from . import sounds
    try:
        return {"file": sounds.save(name, req.data, req.ext)}
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.delete("/api/sounds/{name}")
def sound_remove(name: str):
    from . import sounds
    sounds.remove(name)
    return {"ok": True}


@app.get("/api/usage")
async def usage_summary():
    from . import usage
    await usage.refresh_prices()
    return usage.summary(config.load())


@app.post("/api/usage/reset")
def usage_reset():
    from . import usage
    usage.reset_month()
    return {"ok": True}


@app.post("/api/usage/prices")
async def usage_prices():
    from . import usage
    return {"updated": await usage.refresh_prices(force=True)}


def _job(gen_factory, kind: str, title: str, ref: str = "") -> StreamingResponse:
    """Every AI tool runs as a background job: queued when needed, shown in the activity bar / History /
    Android notification, and it finishes even if the page or app is closed. The page gets the same event
    stream as before (it follows the job)."""
    from . import runs
    import uuid
    try:
        run = runs.start(f"{kind}-{uuid.uuid4().hex[:10]}", (title or kind)[:160], kind, gen_factory, kind=kind, ref=ref or "")
    except runs.TooManyJobs as e:
        raise HTTPException(429, str(e))
    return _follow(run)


async def _job_result(coro_factory, kind: str, title: str, ref: str = "") -> dict:
    """A short AI job whose answer the page waits for (a calculation, a few translated lines)."""
    from . import runs
    import uuid
    box: dict = {}

    async def go(emit) -> None:
        box["result"] = await coro_factory()
        await emit({"type": "done"})
    try:
        run = runs.start(f"{kind}-{uuid.uuid4().hex[:10]}", (title or kind)[:160], kind, go, kind=kind, ref=ref or "")
    except runs.TooManyJobs as e:
        raise HTTPException(429, str(e))
    async for ev in runs.follow(run):
        if ev.get("type") == "error":
            raise HTTPException(400, ev.get("message") or "It didn't work")
        if ev.get("type") == "cancelled":
            raise HTTPException(409, "Cancelled")
    return box.get("result") or {}


def _follow(run) -> StreamingResponse:
    from . import runs

    async def stream():
        async for ev in runs.follow(run):
            yield json.dumps(ev, ensure_ascii=False) + "\n"
    return StreamingResponse(stream(), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/research/active")
def research_active():
    from . import runs
    return {"items": runs.active(), "recent": runs.recent()}


@app.get("/api/research/{rid}/stream")
def research_stream(rid: str):
    from . import runs
    run = runs.RUNS.get(rid)
    if not run:
        raise HTTPException(404, "That search isn't running any more")
    return _follow(run)


@app.post("/api/research/{rid}/cancel")
def research_cancel(rid: str):
    from . import runs
    return {"cancelled": runs.cancel(rid)}


class TranslateReq(BaseModel):
    lang: str
    markdown: str = ""
    id: Optional[str] = None
    items: list = []


# ---------------------------------------------------------------- research toolbar
class FollowupReq(BaseModel):
    id: str
    question: str = ""
    mode: str = "ask"            # ask | compare | timeline | factcheck | elaborate | voice
    selection: str = ""
    ui_lang: Optional[str] = None
    extra: Optional[dict] = None   # elaborate: {formula, expr, result}


@app.post("/api/followup")
async def followup_route(req: FollowupReq):
    from . import followup
    settings = config.load()
    extra = {k: str(v)[:2000] for k, v in (req.extra or {}).items() if k in ("formula", "expr", "result")}

    async def run(emit):
        async for ev in followup.answer(settings, req.id, req.question[:2000], req.mode, req.selection[:4000],
                                        req.ui_lang, extra):
            await emit(ev)
    return _job(run, "followup", req.question or req.mode, req.id)


@app.get("/api/followup/{rid}")
def followup_thread(rid: str):
    from . import followup
    return {"items": followup.thread_of(rid)}


class AddAnswerReq(BaseModel):
    index: int


@app.post("/api/followup/{rid}/add")
def followup_add(rid: str, req: AddAnswerReq):
    from . import followup
    try:
        return followup.add_to_article(config.load(), rid, req.index)
    except ValueError as e:
        raise HTTPException(400, str(e))


class CalcReq(BaseModel):
    text: str


@app.post("/api/tools/calculate")
async def tools_calculate(req: CalcReq):
    """The Calculate button: the selection becomes an expression, the calculator solves it (no long AI answer)."""
    from . import followup

    async def calc() -> dict:
        try:
            return await followup.calculate(config.load(), req.text)
        except (ValueError, asyncio.TimeoutError) as e:
            raise ValueError(f"Couldn't calculate that: {e or 'it took too long'}")
    return await _job_result(calc, "calc", req.text[:80])


class RewriteReq(BaseModel):
    id: str
    selection: str
    instructions: str = ""
    ui_lang: Optional[str] = None


@app.post("/api/rewrite")
async def rewrite_route(req: RewriteReq):
    from . import rewrite
    settings = config.load()

    async def run(emit):
        async for ev in rewrite.rewrite(settings, req.id, req.selection, req.instructions, req.ui_lang):
            await emit(ev)
    return _job(run, "rewrite", req.instructions or req.selection[:80], req.id)


class RegenerateReq(BaseModel):
    id: str
    instructions: str = ""
    keep_edits: bool = True
    length: str = "same"          # same | shorter | longer
    ui_lang: Optional[str] = None


@app.post("/api/regenerate")
async def regenerate_route(req: RegenerateReq):
    """Regenerate article: a background job (queued with searches); the old text stays in the version history."""
    from .regenerate import regenerate
    settings = config.load()
    prompts_mod.use(settings)
    if req.length not in ("same", "shorter", "longer"):
        raise HTTPException(400, "Unknown length")

    async def run(emit):
        async for ev in regenerate(settings, req.id, req.instructions[:1500], req.keep_edits, req.length, req.ui_lang):
            await emit(ev)
    title = req.instructions.strip() or (history.get(req.id) or {}).get("query", "")
    return _job(run, "regenerate", title, req.id)


@app.get("/api/versions/{rid}")
def versions_list(rid: str):
    from . import versions
    return versions.listing(rid)


@app.get("/api/versions/{rid}/{n}")
def versions_get(rid: str, n: int):
    from . import versions
    v = versions.get(rid, n)
    if not v:
        raise HTTPException(404, "No such version")
    return {"n": v["n"], "article": v["article"], "kind": v["kind"], "note": v.get("note", ""), "at": v["at"]}


class VersionReq(BaseModel):
    n: int = 0


@app.post("/api/versions/{rid}/restore")
def versions_restore(rid: str, req: VersionReq):
    from . import versions
    if not versions.restore(rid, req.n):
        raise HTTPException(404, "No such version")
    return versions.listing(rid)


@app.post("/api/versions/{rid}/undo")
def versions_undo(rid: str):
    from . import versions
    if not versions.undo(rid):
        raise HTTPException(400, "There's nothing to undo")
    return versions.listing(rid)


class RewriteApplyReq(BaseModel):
    id: str
    old: str
    new: str
    instructions: str = ""


@app.post("/api/rewrite/apply")
def rewrite_apply(req: RewriteApplyReq):
    from . import rewrite
    try:
        return {"article": rewrite.apply(config.load(), req.id, req.old, req.new, req.instructions)}
    except ValueError as e:
        raise HTTPException(400, str(e))


class ImageReq(BaseModel):
    image: str                  # https://... or data:image/...;base64,...
    question: str = ""
    id: Optional[str] = None
    ui_lang: Optional[str] = None


@app.post("/api/analyze-image")
async def analyze_image(req: ImageReq):
    """'Analyze image': the selected model looks at a picture (an equation, a chart...) and answers."""
    from .llm import get_llm
    s = config.load()
    llm = get_llm(s)
    if not getattr(llm, "supports_vision", False):
        raise HTTPException(400, "The selected AI model can't look at images. Pick a model that can (Claude, GPT-4o/5, "
                                 "or a vision model through OpenRouter), or copy the equation as text with an "
                                 "image-to-text or maths-scanner app.")
    img = req.image.strip()
    if not (img.startswith("https://") or re.match(r"^data:image/(png|jpe?g|webp|gif);base64,", img)):
        raise HTTPException(400, "Only web pictures or screenshots can be analyzed.")
    if len(img) > 8_000_000:
        raise HTTPException(413, "The picture is too large.")
    rec = history.get(req.id) if req.id else None
    lang = languages.answer_language(s, req.ui_lang, req.question or (rec or {}).get("query", ""))
    q = req.question.strip() or ("If the picture shows a formula or equation, write it out in plain maths notation and "
                                 "solve or explain it; otherwise describe what it shows and why it matters here.")
    context = f"The picture is from an article about: {(rec or {}).get('query', '')}\n" if rec else ""
    prompts_mod.use(s)
    system = ("You look at one picture for a reader. Be accurate; if something in the picture is unreadable, say so. "
              f"Write in {lang}.\n" + prompts_mod.SAFETY + "\n" + prompts_mod.UNTRUSTED)

    async def run(emit):
        got = False
        try:
            async for piece in llm.stream(system, llm.vision_content(context + q, [img]), max_tokens=1500):
                got = got or bool(piece.strip())
                await emit({"type": "token", "text": piece})
        except LLMError as e:
            raise ValueError(f"The model couldn't read the picture ({e}). It may not support images: try a "
                             "vision model, or an image-to-text / maths-scanner app.")
        if not got:
            raise ValueError("The model gave no answer for the picture. It may not support images: try a vision "
                             "model, or an image-to-text / maths-scanner app.")
        await emit({"type": "done"})
    return _job(run, "image", req.question or "Analyze image", req.id or "")


class AgentToolsReq(BaseModel):
    agent: Optional[str] = None
    tools: Optional[List[str]] = None
    picker: Optional[str] = None
    effort: Optional[Dict[str, str]] = None


@app.get("/api/agent-tools")
def agent_tools():
    from . import tools as T, effort as E
    s = config.load()
    at = s.get("agent_tools") or {}
    return {"tools": [{"name": t.name, "label": t.label, "help": t.help, "costly": t.costly, "later": t.later}
                      for t in T.REGISTRY.values()],
            "sets": {a: T.enabled(s, a) if (at.get("sets") or {}).get(a) is not None else T.default_sets()[a]
                     for a in T.AGENTS},
            "picker": at.get("picker") or "autonomous",
            "effort": {a: E.level(s, a) for a in E.AGENTS}, "levels": E.ORDER}


@app.post("/api/agent-tools")
def agent_tools_save(req: AgentToolsReq):
    """Tool switches save immediately (no Save button), one set per agent type."""
    from . import tools as T
    s = config.load()
    at = dict(s.get("agent_tools") or {})
    sets = dict(at.get("sets") or {})
    if req.agent:
        if req.agent not in T.AGENTS:
            raise HTTPException(400, "Unknown agent type")
        sets[req.agent] = [n for n in (req.tools or []) if n in T.REGISTRY]
    if req.picker in T.AGENTS:
        at["picker"] = req.picker
    at["sets"] = sets
    if req.effort:
        from . import effort as E
        eff = dict(s.get("effort") or {})
        eff.update({a: v for a, v in req.effort.items() if a in E.AGENTS and v in E.LEVELS})
        config.save({"agent_tools": at, "effort": eff})
        return agent_tools()
    config.save({"agent_tools": at})
    return agent_tools()


@app.post("/api/translate/article")
async def translate_article(req: TranslateReq):
    from . import translate
    settings = config.load()

    async def run(emit):
        async for piece in translate.article(settings, req.markdown, req.lang, req.id):
            await emit({"type": "token", "text": piece})
        await emit({"type": "done"})
    return _job(run, "translate", req.lang, req.id or "")


@app.post("/api/translate/items")
async def translate_items(req: TranslateReq):
    from . import translate

    async def go() -> dict:
        return {"items": await translate.items(config.load(), req.items, req.lang)}
    return await _job_result(go, "translate", req.lang)


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
    return _job(run, "summary", req.query)


class InteractiveReq(BaseModel):
    id: str
    force: bool = False
    ui_lang: Optional[str] = None


@app.post("/api/interactive/start")
async def interactive_start(req: InteractiveReq):
    """Builds the explainer as a background job. Returns the finished page right away when it's
    already built, otherwise the job id to follow (the same job if one is already running)."""
    from . import history as hist, runs
    from .interactive import generate
    rec = hist.get(req.id)
    if not rec or rec.get("outcome") != "article":
        raise HTTPException(404, "Article not found")
    running = runs.find("explainer", req.id)
    if running and not running.finished:
        return {"job": running.id, "running": True}
    if rec.get("interactive_html") and not req.force:
        from .interactive import safe
        return {"html": safe(rec["interactive_html"]), "interactive": rec.get("interactive")}
    settings = config.load()

    async def go(emit) -> None:
        prompts_mod.use(settings)
        await emit({"type": "step", "id": "explainer", "status": "running"})
        try:
            res = await generate(settings, req.id, req.ui_lang, req.force)
        except (ValueError, LLMError) as e:
            await emit({"type": "error", "message": str(e)})
            return
        await emit({"type": "done", "id": req.id, "html": res["html"], "interactive": res.get("interactive")})
    try:
        run = runs.start(f"x-{req.id}", rec.get("query", ""), "explainer", go, kind="explainer", ref=req.id)
    except runs.TooManyJobs as e:
        raise HTTPException(429, str(e))
    return {"job": run.id, "running": False}


@app.post("/api/interactive")
async def interactive_route(req: InteractiveReq):
    """Older route (kept for old pages): builds the explainer as a background job and waits for it."""
    from .interactive import generate
    settings = config.load()
    prompts_mod.use(settings)
    return await _job_result(lambda: generate(settings, req.id, req.ui_lang, req.force), "explainer",
                             (history.get(req.id) or {}).get("query", ""), req.id)


# history
@app.get("/api/history")
def history_list():
    return {"items": history.listing()}


class ExportReq(BaseModel):
    id: str
    title: str = ""
    body_html: str
    explainer: bool = True
    explainer_html: str = ""     # only for articles opened from My library (not in history)
    summary_html: str = ""       # optional short summary shown at the top
    pictures: bool = True
    lang: str = "en"


@app.post("/api/export/html")
async def export_html_route(req: ExportReq):
    """Packs the article (+ explainer) into one standalone HTML file in My library/Exports."""
    from . import export_html
    rec = history.get(req.id) or {"outcome": "article", "interactive_html": req.explainer_html[:2_000_000]}
    if rec.get("outcome") != "article":
        raise HTTPException(404, "Article not found")
    if len(req.body_html) > 3_000_000:
        raise HTTPException(413, "Article too large to export")
    p = await asyncio.to_thread(export_html.export, rec, config.load(), req.body_html, req.title,
                                req.explainer, req.lang, req.summary_html, req.pictures)
    return {"path": str(p), "name": p.name, "size": p.stat().st_size}


class ExportOpenReq(BaseModel):
    name: str
    reveal: bool = False
    kind: str = "export"          # export | summary


class SummaryFileReq(BaseModel):
    title: str = ""
    query: str = ""
    summary: str
    sources: List[dict] = []
    created: str = ""


@app.post("/api/summary-file")
def summary_file(req: SummaryFileReq):
    """Download summary: a small Markdown file with the summary and the sources' links, in My library/Summaries."""
    from . import mylibrary
    if not req.summary.strip():
        raise HTTPException(400, "There's no summary to save yet.")
    p = mylibrary.save_summary(config.load(), req.title[:200], req.query[:500], req.summary[:200_000],
                               req.sources[:100], req.created[:40])
    return {"name": p.name, "size": p.stat().st_size, "path": str(p)}


@app.post("/api/export/open")
def export_open(req: ExportOpenReq):
    from . import export_html
    from . import mylibrary
    p = mylibrary.find_summary(config.load(), req.name) if req.kind == "summary" else export_html.find(config.load(), req.name)
    if not p:
        raise HTTPException(404, "Export not found")
    _open_path(p, reveal=req.reveal)
    return {"ok": True}


class WikiReq(BaseModel):
    api: str
    name: str = ""
    ui_lang: Optional[str] = None


@app.post("/api/wikis/check")
async def wiki_check(req: WikiReq):
    """Checks that an address is a MediaWiki wiki AIRAG can search."""
    from . import wikis
    info = await wikis.site_info(req.api)
    if not info:
        raise HTTPException(400, "That address isn't a wiki AIRAG can search (it needs a MediaWiki api.php).")
    return info


@app.post("/api/wikis/describe")
async def wiki_describe(req: WikiReq):
    from . import wikis
    from .fetch import fetch_page
    from .llm import get_llm
    s = config.load()
    info = await wikis.site_info(req.api)
    if not info:
        raise HTTPException(400, "Wiki not reachable")
    page = await fetch_page(info["main"] or req.api, s["fetch"])
    text, _ = guard.clean(page.text if page.ok else info["name"], s)
    prompts_mod.use(s)
    lang = languages.answer_language(s, req.ui_lang, info["name"])

    async def go() -> dict:
        about = await get_llm(s).complete(*prompts_mod.describe_wiki(info["name"], text, lang), max_tokens=120)
        return {"about": " ".join(about.split())[:240]}
    return await _job_result(go, "summary", info["name"])


class PinSourceReq(BaseModel):
    url: str
    title: str = ""
    query: str = ""
    domain: str = ""
    summary: str = ""
    trust: Optional[float] = None
    published: Optional[str] = None
    site_name: Optional[str] = None


@app.get("/api/pins/sources")
def pinned_sources():
    from . import pinned
    return {"items": pinned.listing()}


@app.post("/api/pins/source")
async def pin_source(req: PinSourceReq):
    """Pins a web page: its text is saved so it can be opened and reused until it's unpinned."""
    from . import pinned
    from .fetch import fetch_page
    if not req.url.startswith(("http://", "https://")):
        raise HTTPException(400, "Only web pages can be pinned.")
    s = config.load()
    page = await fetch_page(req.url, s["fetch"])
    if not page.ok or not page.text.strip():
        raise HTTPException(400, f"Couldn't read the page: {page.error or 'no text'}")
    text, _ = guard.clean(page.text, s)
    item = await asyncio.to_thread(pinned.add, req.url, page.title or req.title, text,
                                   {**req.dict(), "published": req.published or page.published,
                                    "site_name": req.site_name or page.site_name})
    return item


@app.delete("/api/pins/source/{pid}")
def unpin_source(pid: str):
    from . import pinned
    return {"removed": pinned.remove(pid)}


@app.get("/api/pins/source/{pid}")
def pinned_source(pid: str):
    from . import pinned
    item = pinned.get(pid)
    if not item:
        raise HTTPException(404, "Not pinned")
    return item


class PinReq(BaseModel):
    pinned: bool = True


@app.post("/api/history/{rid}/pin")
def history_pin(rid: str, req: PinReq):
    try:
        return {"pinned": history.set_pin(rid, req.pinned)}
    except KeyError:
        raise HTTPException(404, "Not found")


@app.get("/api/history/{rid}")
def history_get(rid: str):
    r = history.get(rid)
    if r is None:
        raise HTTPException(404, "Not found")
    return r


@app.delete("/api/history/{rid}")
def history_delete(rid: str):
    runs.cancel(rid)                          # a task can't keep writing to an article you deleted
    return {"deleted": history.delete(rid)}


@app.delete("/api/history")
def history_clear():
    _busy_guard("Clearing History")
    for r in runs.active():                   # not guarded: running tasks are cancelled first
        runs.cancel(r.id)
    return {"deleted": history.clear()}
