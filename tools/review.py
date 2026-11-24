"""Review before every test build: catches the mistakes token saving could cause.

    python tools/review.py            prints problems; exit code 1 if there are errors

Checks
- Python: undefined names, unused imports that hide typos (pyflakes, if installed), syntax.
- JS: every `import {x} from "./m.js"` names a real file and a real export.
- JS -> server: every literal "/api/..." path the page calls exists as a route.
- i18n: every literal t("key") used in JS exists in en.json; every language has the same keys as en.json
  (missing ones are listed as warnings - English is the fallback).
- Settings: every visible setting is mentioned in SETTINGS.md (by its label) - warnings.
- Rules: SQL text built with f-strings/format/% next to execute(); web requests in modules that never
  check offline.blocked(); innerHTML fed straight from an API result without h()/clean - warnings.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
errors, warnings = [], []


def err(msg):
    errors.append(msg)


def warn(msg):
    warnings.append(msg)


def check_python():
    try:
        import pyflakes  # noqa: F401
    except ImportError:
        warn("pyflakes not installed: Python names not checked (pip install pyflakes)")
        for p in (ROOT / "airag").rglob("*.py"):
            try:
                compile(p.read_text(encoding="utf-8"), str(p), "exec")
            except SyntaxError as e:
                err(f"{p.relative_to(ROOT)}: syntax error: {e}")
        return
    r = subprocess.run([sys.executable, "-m", "pyflakes", "airag", "tools", "tests"], cwd=ROOT,
                       capture_output=True, text=True)
    for line in r.stdout.splitlines():
        if "undefined name" in line or "syntax" in line.lower() or "unable to detect undefined" in line:
            err(line)
        elif "redefinition of unused" in line or "imported but unused" in line:
            continue          # style only
        elif line.strip():
            warn(line)


def check_js():
    from tools.codemap import js_modules
    mods = js_modules()
    for name, info in mods.items():
        for target, names in info["imports"].items():
            if target not in mods:
                err(f"web/js/{name}: imports from missing ./{target}")
                continue
            for n in names:
                if n not in mods[target]["exports"]:
                    err(f"web/js/{name}: imports '{n}' which ./{target} doesn't export")


API = re.compile(r'["`](/api/[A-Za-z0-9_\-/]+)')


def check_routes():
    from tools.codemap import routes
    known = [re.sub(r"\{[^}]+\}", "[^/]+", p) for _, p in routes()]
    pats = [re.compile("^" + k + "$") for k in known]
    for p in sorted((ROOT / "web" / "js").glob("*.js")):
        for m in API.finditer(p.read_text(encoding="utf-8")):
            path = m.group(1).rstrip("/")
            if m.group(0).startswith("`"):            # template: only the fixed part is known
                if not any(k.startswith(path) or path.startswith(k.split("[^/]+")[0].rstrip("/")) for k in known):
                    err(f"web/js/{p.name}: calls {path}… but no route starts like that")
                continue
            if not any(r.match(path) for r in pats) and not any(k.startswith(path + "/") for k in known):
                err(f"web/js/{p.name}: calls {path} but the server has no such route")


TKEY = re.compile(r'\bt\("([a-zA-Z0-9_.\-]+)"')


def check_i18n():
    i18n = ROOT / "web" / "i18n"
    en = json.loads((i18n / "en.json").read_text(encoding="utf-8"))
    for p in sorted((ROOT / "web" / "js").glob("*.js")):
        if p.name == "i18n.js":
            continue
        for k in set(TKEY.findall(p.read_text(encoding="utf-8"))):
            if k not in en and not k.endswith("."):
                err(f"web/js/{p.name}: t(\"{k}\") has no English text")
    for f in sorted(i18n.glob("*.json")):
        if f.name == "en.json":
            continue
        d = json.loads(f.read_text(encoding="utf-8"))
        missing = [k for k in en if k not in d]
        if missing:
            warn(f"web/i18n/{f.name}: {len(missing)} keys fall back to English (e.g. {', '.join(missing[:4])})")


def check_settings_doc():
    from airag import config
    doc = (ROOT / "SETTINGS.md").read_text(encoding="utf-8").lower()
    for sec, fields in config.GENERAL_SCHEMA.items():
        for f in fields:
            if f.get("type") == "hidden" or not f.get("label"):
                continue
            if f["label"].lower() not in doc:
                warn(f"SETTINGS.md: no mention of '{f['label']}' ({sec}.{f['key']})")


SQL_BUILD = re.compile(r"""execute(?:many)?\(\s*(f["']|["'][^"']*["']\s*%\s|["'][^"']*["']\.format\()""")
# modules whose web requests are guarded elsewhere (reviewed): path prefix -> why
OFFLINE_ELSEWHERE = {
    "airag/search/": "search/__init__.py swaps every backend for _OfflineBackend when offline",
    "airag/scholarly.py": "only called from fetch.fetch_page, which checks offline first",
    "airag/youtube.py": "only called from fetch.fetch_page, which checks offline first",
    "airag/ollama_manager.py": "talks to Ollama on this computer",
    "airag/desktop.py": "talks to AIRAG's own local server (127.0.0.1)",
    "airag/llm/": "AI providers are allowed offline (the user picked the writer)",
    "airag/pclink": "the user's own PC over the local network",
}
NET = re.compile(r"\bhttpx\.(AsyncClient|Client|get|post)\b|urllib\.request\.urlopen")


def check_rules():
    for p in (ROOT / "airag").rglob("*.py"):
        s = p.read_text(encoding="utf-8")
        rel = p.relative_to(ROOT).as_posix()
        for i, line in enumerate(s.splitlines(), 1):
            if SQL_BUILD.search(line) and "noqa: sql" not in line:
                err(f"{rel}:{i}: SQL text built from a string format - use bound parameters")
        if NET.search(s) and "offline" not in s and not any(rel.startswith(k) for k in OFFLINE_ELSEWHERE):
            warn(f"{rel}: makes web requests but never checks offline.blocked()")
    risky = re.compile(r"innerHTML\s*=\s*(?:await\s+)?(?:r|res|data|d)\.(?:html|text|body)\b")
    for p in sorted((ROOT / "web" / "js").glob("*.js")):
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if risky.search(line):
                warn(f"web/js/{p.name}:{i}: innerHTML from a server result - make sure it is sanitized")


if __name__ == "__main__":
    for check in (check_python, check_js, check_routes, check_i18n, check_settings_doc, check_rules):
        try:
            check()
        except Exception as e:  # a broken check must not hide the others
            err(f"{check.__name__} failed: {e!r}")
    for w in warnings:
        print("warning:", w)
    for e in errors:
        print("ERROR:", e)
    print(f"review: {len(errors)} errors, {len(warnings)} warnings")
    sys.exit(1 if errors else 0)
