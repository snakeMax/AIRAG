"""PC link: lets the AIRAG phone app use the Ollama models on this PC.

When switched on, a small second server listens on the local network. It only
forwards model listing and chat requests to the local Ollama (nothing else in
AIRAG is reachable through it), and every request must carry the pairing code.
By default only devices on the same home network are accepted.
"""
from __future__ import annotations

import ipaddress
import logging
import secrets
import socket
import threading
import time
from typing import Optional

import httpx

from . import config

log = logging.getLogger("airag.pclink")

ALLOWED = {("GET", "/v1/models"), ("POST", "/v1/chat/completions")}
MAX_BODY = 4 * 1024 * 1024
LOCKOUT_AFTER = 8          # bad codes from one address ...
LOCKOUT_SECONDS = 600      # ... lock it out for 10 minutes

_lock = threading.Lock()
_server = None
_thread: Optional[threading.Thread] = None
_state = {"port": 0, "error": ""}
_failures: dict = {}


def new_code() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # no 0/O/1/I mix-ups
    raw = "".join(secrets.choice(alphabet) for _ in range(12))
    return "-".join(raw[i:i + 4] for i in range(0, 12, 4))


def lan_ips() -> list:
    ips = set()
    try:  # the address used for outgoing traffic (no packet is actually sent)
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    return sorted(ip for ip in ips if not ip.startswith("127.") and ipaddress.ip_address(ip).is_private)


def _client_ok(host: str, allow_internet: bool) -> bool:
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    if allow_internet:
        return True
    return ip.is_private or ip.is_loopback or ip.is_link_local


def _locked_out(host: str) -> bool:
    n, since = _failures.get(host, (0, 0.0))
    if n >= LOCKOUT_AFTER and time.time() - since < LOCKOUT_SECONDS:
        return True
    if n >= LOCKOUT_AFTER:
        _failures.pop(host, None)
    return False


def _fail(host: str) -> None:
    n, since = _failures.get(host, (0, time.time()))
    _failures[host] = (n + 1, time.time() if n + 1 >= LOCKOUT_AFTER else since)


def _make_app(code: str, allow_internet: bool, ollama_url: str):
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse, Response, StreamingResponse
    from starlette.routing import Route

    async def handle(request):
        host = request.client.host if request.client else ""
        if not _client_ok(host, allow_internet):
            return JSONResponse({"error": "Only devices on the same network may connect."}, 403)
        if _locked_out(host):
            return JSONResponse({"error": "Too many wrong pairing codes. Try again later."}, 429)
        auth = request.headers.get("authorization", "")
        given = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        if not secrets.compare_digest(given.upper().encode(), code.encode()):
            _fail(host)
            return JSONResponse({"error": "Wrong pairing code."}, 401)
        _failures.pop(host, None)
        path = request.url.path
        if (request.method, path) not in ALLOWED:
            return JSONResponse({"error": "Not available through PC link."}, 404)
        if path == "/v1/models":
            async with httpx.AsyncClient(timeout=20) as c:
                try:
                    r = await c.get(ollama_url + "/v1/models")
                except httpx.HTTPError:
                    return JSONResponse({"error": "Ollama isn't running on the PC."}, 502)
            return Response(r.content, r.status_code, media_type="application/json")
        body = await request.body()
        if len(body) > MAX_BODY:
            return JSONResponse({"error": "Request too large."}, 413)
        client = httpx.AsyncClient(timeout=httpx.Timeout(900, connect=10))
        try:
            req = client.build_request("POST", ollama_url + "/v1/chat/completions", content=body,
                                       headers={"Content-Type": "application/json"})
            r = await client.send(req, stream=True)
        except httpx.HTTPError:
            await client.aclose()
            return JSONResponse({"error": "Ollama isn't running on the PC."}, 502)

        async def relay():
            try:
                async for chunk in r.aiter_raw():
                    yield chunk
            finally:
                await r.aclose()
                await client.aclose()
        return StreamingResponse(relay(), r.status_code,
                                 media_type=r.headers.get("content-type", "application/json"))

    async def ping(request):
        return JSONResponse({"app": "AIRAG", "pclink": True})

    return Starlette(routes=[Route("/", ping), Route("/{path:path}", handle, methods=["GET", "POST"])])


def _ollama_url(settings: dict) -> str:
    cfg = settings["llm"].get("providers", {}).get("ollama", {})
    return str(cfg.get("base_url") or "http://localhost:11434").rstrip("/")


def _free_port(preferred: int) -> int:
    for p in ([preferred] if preferred else []) + [0]:
        s = socket.socket()
        try:
            s.bind(("0.0.0.0", p))
            port = s.getsockname()[1]
            s.close()
            return port
        except OSError:
            s.close()
    raise RuntimeError("No free port")


def start() -> dict:
    """Start (or restart) the link with the saved settings; creates a code and port the first time."""
    global _server, _thread
    import uvicorn
    stop()
    s = config.load()
    app_cfg = s["app"]
    changed = {}
    if not app_cfg.get("pclink_code"):
        changed["pclink_code"] = new_code()
    port = _free_port(int(app_cfg.get("pclink_port") or 0))
    if port != app_cfg.get("pclink_port"):
        changed["pclink_port"] = port
    changed["pclink_enabled"] = True
    config.save({"app": changed})
    s = config.load()
    app = _make_app(s["app"]["pclink_code"], bool(s["app"].get("pclink_allow_internet")), _ollama_url(s))
    with _lock:
        _server = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=port, log_config=None,
                                                log_level="warning", lifespan="off"))
        _thread = threading.Thread(target=_server.run, daemon=True, name="airag-pclink")
        _thread.start()
    end = time.time() + 5
    while time.time() < end and not _server.started:
        time.sleep(0.05)
    _state.update(port=port, error="" if _server.started else "Couldn't open the port")
    log.info("PC link listening on port %s", port)
    return status()


def stop(save: bool = False) -> None:
    global _server, _thread
    with _lock:
        if _server is not None:
            _server.should_exit = True
            if _thread is not None:
                _thread.join(timeout=5)
        _server, _thread = None, None
    _state["port"] = 0
    if save:
        config.save({"app": {"pclink_enabled": False}})


def new_pairing_code() -> dict:
    config.save({"app": {"pclink_code": new_code()}})
    return start() if running() else status()


def running() -> bool:
    return _server is not None and bool(getattr(_server, "started", False))


def status() -> dict:
    s = config.load()["app"]
    on = running()
    return {"running": on, "enabled": bool(s.get("pclink_enabled")), "port": _state["port"] if on else 0,
            "addresses": lan_ips() if on else [], "code": s.get("pclink_code") or "",
            "allow_internet": bool(s.get("pclink_allow_internet")), "error": _state["error"]}


def autostart() -> None:
    try:
        if config.load()["app"].get("pclink_enabled"):
            start()
    except Exception as e:
        log.warning("PC link didn't start: %s", e)
        _state["error"] = str(e)
