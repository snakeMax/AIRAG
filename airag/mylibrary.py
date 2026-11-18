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

from . import paths, tags

ARTICLES_SUBDIR = "Articles"
SOURCES_SUBDIR = "Sources"
SUMMARIES_SUBDIR = "Summaries"
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
            f"model: {_yaml(rec.get('model', ''))}", "source: AIRAG", f"tags: {tags.yaml_list(rec.get('tags') or [])}", "---", ""]
    if not md.lstrip().startswith("#"):
        head.append(f"# {title}\n")
    lines = ["", "", "## Sources", ""]
    for s in rec.get("article_sources") or []:
        name = (s.get("title") or s.get("domain") or s.get("url") or "").replace("]", ")")
        where = s.get("path") if s.get("local") else s.get("url")
        trust = f" - reliability {s['trust']}/10" if s.get("trust") is not None else ""
        lines.append(f"{s.get('n', '-')}. [{name}]({where}){trust}" if where else f"{s.get('n', '-')}. {name}{trust}")
    lines += ["", "*Written by AI with AIRAG from the sources above. Check them before relying on it.*", ""]
    return "\n".join(head) + md + "\n".join(lines)


def _embed_images(images: List[dict]) -> List[dict]:
    """Download pictures and keep them inside the saved file (as data: URLs), so they work offline."""
    import base64
    import httpx
    from . import offline
    if offline.blocked():
        return []
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


def save_article(rec: dict, settings: dict, rich: bool = False, translations: Optional[List[str]] = None) -> Path:
    """Save as Markdown (text + source links). Next to it goes a small .airag.json copy so the article can be
    opened again in AIRAG; with rich=True that copy also keeps the pictures and the interactive explainer.
    `translations`: languages of the article's translations to keep in the copy (None = all of them)."""
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
    paths.atomic_write_text(target, article_markdown(rec))
    keep = {k: rec.get(k) for k in ("id", "query", "mode", "created", "model", "search", "plan", "title", "article",
                                    "article_sources", "related", "language", "dates", "outcome", "elapsed")}
    keep["sources"] = rec.get("article_sources") or []
    keep["saved_rich"] = bool(rich)
    keep["tags"] = tags.clean(rec.get("tags") or [])
    have = rec.get("translations") or {}
    keep["translations"] = {k: v for k, v in have.items() if translations is None or k in translations}
    if rich:
        keep["images"] = _embed_images(rec.get("images") or [])
        keep["interactive"] = rec.get("interactive")
        keep["interactive_html"] = rec.get("interactive_html") or ""
    else:
        keep["images"], keep["interactive"] = [], None
    paths.atomic_write_text(target.with_name(target.stem + SAVED_SUFFIX), json.dumps(keep, ensure_ascii=False))
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
        out.append({"file": f.name, "id": rec.get("id"), "title": rec.get("title") or rec.get("query"), "query": rec.get("query"),
                    "created": rec.get("created"), "rich": bool(rec.get("saved_rich")), "tags": rec.get("tags") or [],
                    "languages": sorted((rec.get("translations") or {}).keys()),
                    "has_md": f.with_name(f.name[: -len(SAVED_SUFFIX)] + ".md").exists()})
    return out


def load_saved(settings: dict, name: str) -> dict:
    import json
    d = (folder(settings) / ARTICLES_SUBDIR).resolve()
    f = (d / Path(name).name).resolve()          # only files directly inside My library/Articles
    if f.parent != d or not f.name.endswith(SAVED_SUFFIX) or not f.is_file():
        raise FileNotFoundError("Saved article not found")
    rec = json.loads(f.read_text(encoding="utf-8"))
    md_file = f.with_name(f.name[: -len(SAVED_SUFFIX)] + ".md")
    rec["saved_file"] = f.name
    rec["saved_path"] = str(md_file)
    rec["edited_outside"] = _reread_markdown(rec, f, md_file)
    if settings["library"].get("reopen_to_history", True) and rec.get("id"):
        _back_to_history(rec)
    return rec


def _reread_markdown(rec: dict, json_file: Path, md_file: Path) -> bool:
    """If the .md was changed after saving (e.g. edited in Obsidian), the article is read from it again and the
    AIRAG copy is updated to match."""
    import json
    from . import openfile
    try:
        if not md_file.is_file() or md_file.stat().st_mtime <= json_file.stat().st_mtime + 1:
            return False
        new = openfile.parse_markdown(md_file.read_text(encoding="utf-8", errors="replace"), md_file.name)
    except (OSError, ValueError):
        return False
    new_tags = [t for t in new.get("tags") or [] if t != tags.DEFAULT]
    if (new["article"].strip() == (rec.get("article") or "").strip() and new["title"] == rec.get("title")
            and new_tags == (rec.get("tags") or [])):
        return False
    rec["article"], rec["title"], rec["tags"] = new["article"], new["title"], new_tags
    if new["article_sources"]:
        old = {s.get("n"): s for s in rec.get("article_sources") or []}
        rec["article_sources"] = [{**old.get(s["n"], {}), **s} for s in new["article_sources"]]
        rec["sources"] = rec["article_sources"]
    keep = {k: v for k, v in rec.items() if k not in ("saved_file", "saved_path", "edited_outside")}
    try:
        paths.atomic_write_text(json_file, json.dumps(keep, ensure_ascii=False))
    except OSError:
        pass
    return True


def _back_to_history(rec: dict) -> None:
    """Reopening a saved article puts it back in History (if it had dropped out), so the toolbar works on it."""
    from . import history
    try:
        cur = history.get(rec["id"])
        if cur:
            if rec.get("edited_outside"):       # keep the answers thread and anything else History knows
                from . import versions

                def take(cur: dict) -> None:
                    before, before_src = cur.get("article") or "", cur.get("article_sources")
                    cur.update({k: rec[k] for k in ("article", "title", "article_sources", "sources", "tags") if k in rec})
                    versions.note_change(cur, before, "edit", "Edited outside AIRAG", before_src)
                history.update(rec["id"], take)
            return
        entry = {k: v for k, v in rec.items() if k not in ("saved_file", "edited_outside")}
        entry.update({"outcome": "article", "status": "done"})
        history.save(entry)
    except Exception:
        pass


def set_tags(rec: dict, settings: dict) -> None:
    """New tags on a saved article: the Markdown properties and the AIRAG copy are updated in place."""
    import json
    md = Path(rec.get("saved_path") or "")
    d = (folder(settings) / ARTICLES_SUBDIR).resolve()
    if not md.is_file() or md.resolve().parent != d:
        return
    text = md.read_text(encoding="utf-8", errors="replace")
    line = f"tags: {tags.yaml_list(rec.get('tags') or [])}"
    if text.startswith("---") and text.find("\n---", 3) > 0:
        end = text.find("\n---", 3)
        head, rest = text[:end], text[end:]
        head = re.sub(r"(?ms)^tags[ \t]*:[ \t]*(\[.*?\]|[^\n]*)(\n[ \t]*-[^\n]*)*", line, head, count=1) \
            if re.search(r"(?m)^tags[ \t]*:", head) else head + "\n" + line
        text = head + rest
    paths.atomic_write_text(md, text)
    js = md.with_name(md.stem + SAVED_SUFFIX)
    try:
        data = json.loads(js.read_text(encoding="utf-8"))
        data["tags"] = tags.clean(rec.get("tags") or [])
        paths.atomic_write_text(js, json.dumps(data, ensure_ascii=False))
    except (OSError, ValueError):
        pass
    try:                                 # so the copy isn't seen as "edited outside AIRAG"
        import os
        st = js.stat()
        os.utime(md, (st.st_atime, st.st_mtime))
    except OSError:
        pass


def summary_markdown(title: str, query: str, summary: str, sources: List[dict], when: str = "") -> str:
    """A small, plain file: the summary and the sources' links. Opens anywhere (and in AIRAG)."""
    summary = re.sub(r"<think>.*?</think>", "", summary or "", flags=re.S).strip()
    day = (when or dt.date.today().isoformat())[:10]
    lines = ["---", f"title: {_yaml(title)}", f"search: {_yaml(query)}", f"created: {day}", "kind: summary",
             "source: AIRAG", "---", "", f"# {title}", "", summary, ""]
    rows = []
    for i, s in enumerate(sources or [], 1):
        url = str(s.get("url") or "")
        if not url.startswith(("http://", "https://")):
            continue
        name = str(s.get("title") or s.get("domain") or url).replace("]", ")").replace("\n", " ")[:200]
        rows.append(f"{s.get('n') or i}. [{name}]({url})")
    if rows:
        lines += ["## Sources", ""] + rows + [""]
    lines += ["*Summary written by AI with AIRAG. Check the sources before relying on it.*", ""]
    return "\n".join(lines)


def save_summary(settings: dict, title: str, query: str, summary: str, sources: List[dict], when: str = "") -> Path:
    d = ensure(settings) / SUMMARIES_SUBDIR
    d.mkdir(parents=True, exist_ok=True)
    day = (when or dt.date.today().isoformat())[:10]
    target = d / f"{day} {_safe_name(title or query or 'Summary')} (summary).md"
    paths.atomic_write_text(target, summary_markdown(title, query, summary, sources, when))
    return target


def find_summary(settings: dict, name: str) -> Optional[Path]:
    d = (ensure(settings) / SUMMARIES_SUBDIR).resolve()
    p = (d / Path(name).name).resolve()
    return p if p.parent == d and p.suffix == ".md" and p.is_file() else None


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


_import_lock = __import__("threading").Lock()


def _same_file(a: Path, b: Path) -> bool:
    import hashlib
    try:
        if a.stat().st_size != b.stat().st_size:
            return False
        h = []
        for p in (a, b):
            d = hashlib.sha256()
            with open(p, "rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    d.update(chunk)
            h.append(d.digest())
        return h[0] == h[1]
    except OSError:
        return False


def import_files(files: List[str], settings: dict, move: bool = False) -> List[str]:
    """Copy (or move) files into My library. Returns the new paths.
    Never overwrites: a different file with the same name gets " (2)" etc.; an identical file that's already there
    is skipped (no duplicates); a file that's already inside My library isn't copied onto itself."""
    d = ensure(settings).resolve()
    out = []
    with _import_lock:                       # two imports at once can't pick the same new name
        for f in files:
            src = Path(f)
            if not src.is_file():
                continue
            if d in src.resolve().parents:
                continue
            dest = d / src.name
            n = 2
            duplicate = False
            while dest.exists():
                if _same_file(src, dest):
                    duplicate = True
                    break
                dest = d / f"{src.stem} ({n}){src.suffix}"
                n += 1
            if duplicate:
                if move:
                    try:
                        src.unlink()        # the same file is already in My library
                    except OSError:
                        pass
                continue
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


# ---------------------------------------------------------------- unsaving (with a "recently removed" cache)
# Unsaving takes an article out of My library/Articles (its .md and AIRAG copy) but keeps it in History. The files
# are moved to a private "recently removed" folder outside My library (not indexed, not synced), so an accidental
# unsave can be restored exactly as it was. Kept for REMOVED_DAYS days, at most REMOVED_MAX entries.
REMOVED_DAYS = 30
REMOVED_MAX = 50
_RID = re.compile(r"^[\w\-]{6,80}$")


def removed_dir() -> Path:
    return paths.LOCAL_DIR / "removed-saved"


def _articles(settings: dict) -> Path:
    return (folder(settings) / ARTICLES_SUBDIR).resolve()


def find_saved(settings: dict, rid: str = "", file: str = "", md_path: str = "") -> Optional[Path]:
    """The .airag.json of a saved article, by its file name, its .md path or its History id."""
    import json
    d = _articles(settings)
    if file:
        f = (d / Path(file).name).resolve()
        if f.parent == d and f.name.endswith(SAVED_SUFFIX) and f.is_file():
            return f
    if md_path:
        p = Path(md_path)
        f = (d / (p.stem + SAVED_SUFFIX)).resolve()
        if p.suffix.lower() == ".md" and f.parent == d and f.is_file():
            return f
    if rid and d.is_dir():
        for f in sorted(d.glob("*" + SAVED_SUFFIX), key=lambda x: x.stat().st_mtime, reverse=True):
            try:
                if json.loads(f.read_text(encoding="utf-8")).get("id") == rid:
                    return f
            except (OSError, ValueError):
                continue
    return None


def unsave(settings: dict, json_file: Path) -> dict:
    """Moves a saved article out of My library into the "recently removed" cache; History keeps it."""
    import json
    import time
    from . import history
    stem = json_file.name[: -len(SAVED_SUFFIX)]
    md = json_file.with_name(stem + ".md")
    try:
        rec = json.loads(json_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        rec = {}
    if md.is_file() and rec:                        # edits made in another editor are kept in the copy
        _reread_markdown(rec, json_file, md)
    rid = f"{time.strftime('%Y%m%d-%H%M%S')}-{secrets_token()}"
    dest = removed_dir() / rid
    dest.mkdir(parents=True, exist_ok=True)
    moved = []
    for f in (md, json_file):
        if f.is_file():
            shutil.move(str(f), str(dest / f.name))
            moved.append(f.name)
    meta = {"rid": rid, "id": rec.get("id"), "title": rec.get("title") or rec.get("query") or stem, "query": rec.get("query"),
            "created": rec.get("created"), "removed": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "files": moved, "tags": rec.get("tags") or []}
    paths.atomic_write_text(dest / "removed.json", json.dumps(meta, ensure_ascii=False))
    if rec.get("id"):                               # stays in History, now as an unsaved article
        if history.get(rec["id"]):
            history.update(rec["id"], {"saved_path": None})
        else:
            entry = {k: v for k, v in rec.items() if k not in ("saved_file", "edited_outside", "saved_path")}
            entry.update({"outcome": "article", "status": "done"})
            try:
                history.save(entry)
            except Exception:
                pass
    purge_removed()
    return meta


def secrets_token() -> str:
    import secrets
    return secrets.token_hex(3)


def list_removed() -> List[dict]:
    import json
    out = []
    d = removed_dir()
    for sub in sorted(d.iterdir(), reverse=True) if d.is_dir() else []:
        try:
            out.append(json.loads((sub / "removed.json").read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return out


def restore(settings: dict, rid: str) -> Path:
    """Puts an unsaved article back in My library/Articles (a free name if one is taken now)."""
    import json
    from . import history
    if not _RID.match(rid or ""):
        raise FileNotFoundError("Not found")
    src = (removed_dir() / rid).resolve()
    if src.parent != removed_dir().resolve() or not src.is_dir():
        raise FileNotFoundError("This article is no longer in Recently removed")
    meta = json.loads((src / "removed.json").read_text(encoding="utf-8"))
    d = ensure(settings) / ARTICLES_SUBDIR
    d.mkdir(parents=True, exist_ok=True)
    js = next((f for f in src.iterdir() if f.name.endswith(SAVED_SUFFIX)), None)
    if js is None:
        raise FileNotFoundError("The saved copy is missing")
    stem = js.name[: -len(SAVED_SUFFIX)]
    base, n, new_stem = stem, 2, stem
    while (d / f"{new_stem}.md").exists() or (d / f"{new_stem}{SAVED_SUFFIX}").exists():
        new_stem = f"{base} ({n})"
        n += 1
    md_src = src / f"{stem}.md"
    if md_src.is_file():
        shutil.move(str(md_src), str(d / f"{new_stem}.md"))
    shutil.move(str(js), str(d / f"{new_stem}{SAVED_SUFFIX}"))
    shutil.rmtree(src, ignore_errors=True)
    md = d / f"{new_stem}.md"
    try:                                            # the copy mustn't look "edited outside AIRAG"
        import os
        st = (d / f"{new_stem}{SAVED_SUFFIX}").stat()
        if md.exists():
            os.utime(md, (st.st_atime, st.st_mtime))
    except OSError:
        pass
    if meta.get("id") and history.get(meta["id"]):
        history.update(meta["id"], {"saved_path": str(md)})
    return md


def forget_removed(rid: str) -> bool:
    if not _RID.match(rid or ""):
        return False
    p = (removed_dir() / rid).resolve()
    if p.parent == removed_dir().resolve() and p.is_dir():
        shutil.rmtree(p, ignore_errors=True)
        return True
    return False


def purge_removed() -> None:
    import time
    d = removed_dir()
    if not d.is_dir():
        return
    subs = sorted((p for p in d.iterdir() if p.is_dir()), reverse=True)
    for i, p in enumerate(subs):
        try:
            old = time.time() - p.stat().st_mtime > REMOVED_DAYS * 86400
        except OSError:
            continue
        if old or i >= REMOVED_MAX:
            shutil.rmtree(p, ignore_errors=True)
