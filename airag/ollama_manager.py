"""Find, start and manage a local Ollama runtime (and its models)."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import httpx

from .paths import PACKAGE_DATA

log = logging.getLogger("airag.ollama")
DEFAULT_URL = "http://localhost:11434"
DOWNLOAD_URL = "https://ollama.com/download"
_start_lock = asyncio.Lock()


def find_executable() -> Optional[str]:
    exe = shutil.which("ollama")
    if exe:
        return exe
    candidates = []
    if sys.platform == "win32":
        for base in (os.environ.get("LOCALAPPDATA"), os.environ.get("ProgramFiles"), os.environ.get("ProgramW6432")):
            if base:
                candidates += [Path(base) / "Programs" / "Ollama" / "ollama.exe", Path(base) / "Ollama" / "ollama.exe"]
    elif sys.platform == "darwin":
        candidates += [Path("/Applications/Ollama.app/Contents/Resources/ollama"), Path("/usr/local/bin/ollama"),
                       Path("/opt/homebrew/bin/ollama")]
    else:
        candidates += [Path("/usr/local/bin/ollama"), Path("/usr/bin/ollama")]
    for c in candidates:
        if c.exists():
            return str(c)
    return None


def is_local(base_url: str) -> bool:
    host = (urlparse(base_url or DEFAULT_URL).hostname or "").lower()
    return host in ("localhost", "127.0.0.1", "::1", "0.0.0.0")


async def version(base_url: str) -> Optional[str]:
    try:
        async with httpx.AsyncClient(timeout=3) as c:
            r = await c.get(base_url.rstrip("/") + "/api/version")
        return r.json().get("version", "?") if r.status_code == 200 else None
    except Exception:
        return None


async def list_models(base_url: str) -> list:
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(base_url.rstrip("/") + "/api/tags")
    r.raise_for_status()
    out = []
    for m in r.json().get("models", []):
        d = m.get("details") or {}
        out.append({"name": m.get("name"), "size": m.get("size", 0), "modified": m.get("modified_at"),
                    "parameters": d.get("parameter_size", ""), "quantization": d.get("quantization_level", ""),
                    "family": d.get("family", "")})
    return sorted(out, key=lambda x: x["name"] or "")


async def status(base_url: str) -> dict:
    base_url = base_url or DEFAULT_URL
    ver = await version(base_url)
    models = []
    if ver:
        try:
            models = await list_models(base_url)
        except Exception:
            pass
    return {"installed": bool(find_executable()) or bool(ver), "running": bool(ver), "version": ver,
            "executable": find_executable(), "local": is_local(base_url), "models": models,
            "download_url": DOWNLOAD_URL, "ram_gb": total_ram_gb()}


def _spawn(exe: str) -> None:
    kw: dict = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if sys.platform == "win32":
        kw["creationflags"] = 0x08000000 | 0x00000200  # CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
    else:
        kw["start_new_session"] = True
    subprocess.Popen([exe, "serve"], **kw)


async def ensure_running(base_url: str, timeout: float = 25) -> bool:
    """Start `ollama serve` in the background if it isn't running. Returns True when reachable."""
    base_url = base_url or DEFAULT_URL
    if await version(base_url):
        return True
    if not is_local(base_url):
        return False
    async with _start_lock:
        if await version(base_url):
            return True
        exe = find_executable()
        if not exe:
            return False
        log.info("starting Ollama: %s serve", exe)
        try:
            _spawn(exe)
        except OSError as e:
            log.warning("couldn't start Ollama: %s", e)
            return False
        loop = asyncio.get_running_loop()
        end = loop.time() + timeout
        while loop.time() < end:
            await asyncio.sleep(0.7)
            if await version(base_url):
                return True
    return False


async def pull(base_url: str, model: str, job) -> None:
    """Download a model, reporting progress to a Job."""
    job.message = f"Downloading {model}"
    async with httpx.AsyncClient(timeout=httpx.Timeout(None, connect=15)) as c:
        async with c.stream("POST", base_url.rstrip("/") + "/api/pull", json={"model": model, "stream": True}) as r:
            if r.status_code >= 400:
                raise RuntimeError((await r.aread()).decode(errors="replace")[:300])
            async for line in r.aiter_lines():
                if job.cancelled:
                    raise asyncio.CancelledError()
                if not line.strip():
                    continue
                d = json.loads(line)
                if d.get("error"):
                    raise RuntimeError(d["error"])
                job.detail = d.get("status", "")
                if d.get("total"):
                    job.progress = min(1.0, (d.get("completed") or 0) / d["total"])
                    job.extra = {"completed": d.get("completed") or 0, "total": d["total"]}
    job.progress = 1.0
    job.message = f"{model} is ready"


async def delete(base_url: str, model: str) -> None:
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.request("DELETE", base_url.rstrip("/") + "/api/delete", json={"model": model})
    if r.status_code >= 400:
        raise RuntimeError(r.text[:300])


def recommended() -> dict:
    data = json.loads((PACKAGE_DATA / "ollama_models.json").read_text(encoding="utf-8"))
    ram = total_ram_gb()
    try:
        from .hardware import best_vram_gb
        vram = best_vram_gb()
    except Exception:
        vram = 0.0
    models = data["models"]
    fitting = [m for m in models if ram and m["min_ram_gb"] <= ram + 0.6]
    pick = None
    for name in data.get("preference", []):  # best model that fits this PC
        m = next((x for x in fitting if x["name"] == name), None)
        if m:
            pick = m["name"]
            break
    if vram >= 4:   # prefer the best model that fits in graphics memory: much faster than running on the CPU
        for name in data.get("preference", []):
            m = next((x for x in fitting if x["name"] == name and x.get("size_gb", 99) <= vram * 0.9), None)
            if m:
                pick = m["name"]
                break
    for m in models:
        m["fits"] = (not ram) or m["min_ram_gb"] <= ram + 0.6
        m["gpu"] = bool(vram and m.get("size_gb", 99) <= vram * 0.9)
        m["recommended"] = m["name"] == pick
    return {"ram_gb": ram, "vram_gb": vram, "models": models, "note": data.get("note", "")}


def total_ram_gb() -> float:
    try:
        if sys.platform == "win32":
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            st = MEMORYSTATUSEX()
            st.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))
            return round(st.ullTotalPhys / 1024 ** 3, 1)
        if sys.platform == "darwin":
            out = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=5).stdout
            return round(int(out.strip()) / 1024 ** 3, 1)
        return round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1024 ** 3, 1)
    except Exception:
        return 0.0
