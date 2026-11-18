"""What this computer or phone has: processor, memory, graphics card(s) and free disk space.
Shown in Settings -> System and used to recommend Ollama models. No external tools are
required; nvidia-smi is used when present for exact graphics memory."""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from typing import List, Optional

from . import __version__, paths

_cache: Optional[dict] = None


def _cpu_name() -> str:
    try:
        if sys.platform == "win32":
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as k:
                return str(winreg.QueryValueEx(k, "ProcessorNameString")[0]).strip()
        if sys.platform == "darwin":
            return subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True,
                                  timeout=5).stdout.strip()
        with open("/proc/cpuinfo", encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.lower().startswith(("model name", "hardware", "processor\t: a")):
                    return line.split(":", 1)[1].strip()
    except Exception:
        pass
    return platform.processor() or platform.machine()


def _nvidia() -> List[dict]:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return []
    try:
        kw = {"creationflags": 0x08000000} if sys.platform == "win32" else {}
        out = subprocess.run([exe, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=8, **kw).stdout
    except Exception:
        return []
    gpus = []
    for line in out.splitlines():
        name, _, mem = line.rpartition(",")
        if name.strip():
            try:
                gpus.append({"name": name.strip(), "vram_gb": round(int(mem.strip()) / 1024, 1), "source": "nvidia-smi"})
            except ValueError:
                gpus.append({"name": name.strip(), "vram_gb": None, "source": "nvidia-smi"})
    return gpus


def _windows_gpus() -> List[dict]:
    """Display adapters from the registry, with dedicated memory (works for NVIDIA, AMD and Intel)."""
    import winreg
    base = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
    gpus, seen = [], set()
    try:
        root = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base)
    except OSError:
        return []
    with root:
        for i in range(64):
            try:
                sub = winreg.EnumKey(root, i)
            except OSError:
                break
            if not sub.isdigit():
                continue
            try:
                with winreg.OpenKey(root, sub) as k:
                    name = str(winreg.QueryValueEx(k, "DriverDesc")[0])
                    mem = None
                    for value in ("HardwareInformation.qwMemorySize", "HardwareInformation.MemorySize"):
                        try:
                            raw = winreg.QueryValueEx(k, value)[0]
                            mem = int.from_bytes(raw, "little") if isinstance(raw, bytes) else int(raw)
                            break
                        except OSError:
                            continue
            except OSError:
                continue
            if name in seen or "basic display" in name.lower() or "remote" in name.lower():
                continue
            seen.add(name)
            gpus.append({"name": name, "vram_gb": round(mem / 1024 ** 3, 1) if mem else None, "source": "windows"})
    return gpus


def _gpus() -> List[dict]:
    if paths.ANDROID:
        return []
    nv = _nvidia()
    other = _windows_gpus() if sys.platform == "win32" else []
    names = {g["name"] for g in nv}
    return nv + [g for g in other if g["name"] not in names]


def _disk(path) -> Optional[dict]:
    try:
        p = path
        while not os.path.exists(p) and os.path.dirname(p) != p:
            p = os.path.dirname(p)
        u = shutil.disk_usage(p)
        return {"path": str(path), "free_gb": round(u.free / 1024 ** 3, 1), "total_gb": round(u.total / 1024 ** 3, 1)}
    except OSError:
        return None


def info(refresh: bool = False) -> dict:
    global _cache
    if _cache and not refresh:
        return _cache
    from .ollama_manager import total_ram_gb
    from . import build_info
    out = {"app_version": __version__, "build": build_info(), "platform": paths.PLATFORM, "python": platform.python_version(),
           "os": f"{platform.system()} {platform.release()}".strip(), "machine": platform.machine(),
           "cpu": _cpu_name(), "cores": os.cpu_count() or 0, "ram_gb": total_ram_gb(), "gpus": _gpus(),
           "disks": [d for d in (_disk(paths.CONFIG_DIR), _disk(paths.LOCAL_DIR)) if d]}
    if paths.ANDROID:
        try:
            from .android_bridge import device_info
            out["device"] = device_info()
            out["ram_gb"] = out["device"].get("ram_gb") or out["ram_gb"]
            out["os"] = f"Android {out['device'].get('android', '')}".strip()
        except Exception:
            pass
    # unique disks only
    seen, disks = set(), []
    for d in out["disks"]:
        key = (d["total_gb"], d["free_gb"])
        if key not in seen:
            seen.add(key)
            disks.append(d)
    out["disks"] = disks
    _cache = out
    return out


def best_vram_gb() -> float:
    vals = [g["vram_gb"] for g in info().get("gpus", []) if g.get("vram_gb")]
    return max(vals) if vals else 0.0
