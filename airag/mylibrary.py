"""My library: the user's own folder for saved articles and imported files.

It can live on any drive, separate from AIRAG's settings folder, and it's always
included when "My library" searches run (alongside any other folders the user added).
Saved articles are small Markdown files (text and source links only, no page copies
or images) that also work as notes in Obsidian.
"""
from __future__ import annotations

import datetime as dt
import re
import shutil
from pathlib import Path
from typing import List, Optional

from . import paths

ARTICLES_SUBDIR = "Articles"
SOURCES_SUBDIR = "Sources"
SAVED_SUFFIX = ".airag.json"     # full copy of a saved article, so AIRAG can show it again without the AI
MAX_IMAGE_BYTES = 800_000
MAX_IMAGES = 8


def default_dir() -> Path:
    if paths.ANDROID:
        # apps may create their own files in the shared Documents folder without extra permissions
        return Path("/storage/emulated/0/Documents/AIRAG Library")
    return Path.home() / "Documents" / "AIRAG Library"


def folder(settings: dict) -> Path:
    custom = str(settings.get("library", {}).get("personal_folder") or "").strip()
    return Path(custom).expanduser() if custom else default_dir()


def ensure(settings: dict) -> Path:
    d = folder(settings)
    (d / ARTICLES_SUBDIR).mkdir(parents=True, exist_ok=True)
    return d


def _safe_name(text: str, limit: int = 80) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f#^\[\]]+', " ", text).strip().strip(".")
    return re.sub(r"\s+", " ", name)[:limit].strip() or "Article"


def _yaml(v: str) -> str:
    return '"' + str(v).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ") + '"'


def article_markdown(rec: dict) -> str:
    """The article as Markdown with a small header (Obsidian-style properties) and the sources at the bottom."""
    md = re.sub(r"<think>.*?</think>", "", rec.get("article") or "", flags=re.S).strip()
    title = rec.get("title") or rec.get("query") or "Article"
    created = rec.get("created") or dt.datetime.now().astimezone().isoformat(timespec="seconds")
    head = ["---", f"title: {_yaml(title)}", f"search: {_yaml(rec.get('query', ''))}", f"created: {created}",
            f"model: {_yaml(rec.get('model', ''))}", "source: AIRAG", "tags: [airag]", "---", ""]
    if not md.lstrip().startswith("#"):
        head.append(f"# {title}\n")
    lines = ["", "", "## Sources", ""]
    for s in rec.get("article_sources") or []:
        name = (s.get("title") or s.get("domain") or s.get("url") or "").replace("]", ")")
        where = s.get("path") if s.get("local") else s.get("url")
        trust = f" - reliability {s['trust']}/10" if s.get("trust") is not None else ""
        lines.append(f"{s.get('n', '-')}. [{name}]({where}){trust}" if where else f"{s.get('n', '-')}. {name}{trust}")
    lines += ["", f"*Written by AI with AIRAG from the sources above. Check them before relying on it.*", ""]
    return "\n".join(head) + md + "\n".join(lines)


def _embed_images(images: List[dict]) -> List[dict]:
    """Download pictures and keep them inside the saved file (as data: URLs), so they work offline."""
    import base64
    import httpx
    out = []
    with httpx.Client(timeout=15, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0 AIRAG"}) as c:
        for im in images[:MAX_IMAGES]:
            try:
                r = c.get(im["src"])
                ctype = r.headers.get("content-type", "").split(";")[0]
                if r.status_code == 200 and ctype.startswith("image/") and len(r.content) <= MAX_IMAGE_BYTES:
                    data = f"data:{ctype};base64," + base64.b64encode(r.content).decode()
                    out.append({**im, "src": data, "thumb": data, "original_src": im["src"]})
            except Exception:
                continue
    return out


def save_article(rec: dict, settings: dict, rich: bool = False) -> Path:
    """Save as Markdown (text + source links). Next to it goes a small .airag.json copy so the article can be
    opened again in AIRAG; with rich=True that copy also keeps the pictures and the interactive explainer."""
    import json
    if rec.get("outcome") != "article" or not rec.get("article"):
        raise ValueError("Only finished articles can be saved.")
    d = ensure(settings) / ARTICLES_SUBDIR
    day = str(rec.get("created") or dt.date.today().isoformat())[:10]
    base = f"{day} {_safe_name(rec.get('title') or rec.get('query') or 'Article')}"
    target = d / f"{base}.md"
    old = rec.get("saved_path")
    if old and Path(old).parent == d:
        target = Path(old)          # saving again updates the same file
    else:
        n = 2
        while target.exists():
            target = d / f"{base} ({n}).md"
            n += 1
    target.write_text(article_markdown(rec), encoding="utf-8")
    keep = {k: rec.get(k) for k in ("id", "query", "mode", "created", "model", "search", "plan", "title", "article",
                                    "article_sources", "related", "language", "dates", "outcome", "elapsed")}
    keep["sources"] = rec.get("article_sources") or []
    keep["saved_rich"] = bool(rich)
    if rich:
        keep["images"] = _embed_images(rec.get("images") or [])
        keep["interactive"] = rec.get("interactive")
        keep["interactive_html"] = rec.get("interactive_html") or ""
    else:
        keep["images"], keep["interactive"] = [], None
    target.with_name(target.stem + SAVED_SUFFIX).write_text(json.dumps(keep, ensure_ascii=False), encoding="utf-8")
    return target


def list_saved(settings: dict) -> List[dict]:
    import json
    d = folder(settings) / ARTICLES_SUBDIR
    out = []
    for f in sorted(d.glob("*" + SAVED_SUFFIX), key=lambda p: p.stat().st_mtime, reverse=True) if d.is_dir() else []:
        try:
            rec = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        out.append({"file": f.name, "title": rec.get("title") or rec.get("query"), "query": rec.get("query"),
                    "created": rec.get("created"), "rich": bool(rec.get("saved_rich")),
                    "has_md": f.with_name(f.name[: -len(SAVED_SUFFIX)] + ".md").exists()})
    return out


def load_saved(settings: dict, name: str) -> dict:
    import json
    d = (folder(settings) / ARTICLES_SUBDIR).resolve()
    f = (d / Path(name).name).resolve()          # only files directly inside My library/Articles
    if f.parent != d or not f.name.endswith(SAVED_SUFFIX) or not f.is_file():
        raise FileNotFoundError("Saved article not found")
    rec = json.loads(f.read_text(encoding="utf-8"))
    rec["saved_file"] = f.name
    rec["saved_path"] = str(f.with_name(f.name[: -len(SAVED_SUFFIX)] + ".md"))
    return rec


def source_markdown(page, query: str = "") -> str:
    """A light, readable copy of a web page: title, link, date and the main text only."""
    title = page.title or page.final_url or page.url
    head = ["---", f"title: {_yaml(title)}", f"url: {page.final_url or page.url}"]
    if page.published:
        head.append(f"published: {_yaml(page.published)}")
    if page.author:
        head.append(f"author: {_yaml(page.author)}")
    head += [f"saved: {dt.datetime.now().astimezone().isoformat(timespec='seconds')}"]
    if query:
        head.append(f"search: {_yaml(query)}")
    head += ["source: AIRAG", "tags: [airag, source]", "---", "", f"# {title}", "",
             f"Original page: <{page.final_url or page.url}>", ""]
    return "\n".join(head) + "\n" + (page.text or "").strip() + "\n"


def save_source(page, settings: dict, query: str = "") -> Path:
    d = ensure(settings) / SOURCES_SUBDIR
    d.mkdir(parents=True, exist_ok=True)
    from urllib.parse import urlparse
    host = urlparse(page.final_url or page.url).netloc.replace("www.", "")
    base = _safe_name(f"{page.title or host} - {host}" if page.title else host)
    target = d / f"{base}.md"
    n = 2
    while target.exists():
        target = d / f"{base} ({n}).md"
        n += 1
    target.write_text(source_markdown(page, query), encoding="utf-8")
    return target


def import_files(files: List[str], settings: dict, move: bool = False) -> List[str]:
    """Copy (or move) files into My library. Returns the new paths."""
    d = ensure(settings)
    out = []
    for f in files:
        src = Path(f)
        if not src.is_file():
            continue
        dest = d / src.name
        n = 2
        while dest.exists():
            dest = d / f"{src.stem} ({n}){src.suffix}"
            n += 1
        (shutil.move if move else shutil.copy2)(str(src), str(dest))
        out.append(str(dest))
    return out


def status(settings: dict) -> dict:
    d = folder(settings)
    exists = d.is_dir()
    count = 0
    if exists:
        try:
            count = sum(1 for p in d.rglob("*") if p.is_file())
        except OSError:
            pass
    return {"path": str(d), "default": str(default_dir()), "custom": bool(settings["library"].get("personal_folder")),
            "exists": exists, "files": count}


def resolve_saved(rec: dict) -> Optional[str]:
    p = rec.get("saved_path")
    return p if p and Path(p).is_file() else None
