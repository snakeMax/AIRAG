"""Open files with AIRAG: Markdown articles, saved .airag.json copies and exported web pages.

Opening never uses the AI. The file becomes an article in History, so the reader can use the toolbar on it
(follow-ups, rewrite, cite...). Everything in an opened file is treated as untrusted text:
- AIRAG's own Markdown files are read back into article + sources;
- other Markdown files open as a plain article with no sources;
- AIRAG's exported web pages carry a data copy of the article (plain JSON, never run); other web pages and older
  exports fall back to text extraction;
- an interactive explainer is only kept from AIRAG's own My library (code from elsewhere is never loaded).
"""
from __future__ import annotations

import datetime as dt
import json
import re
import uuid
from pathlib import Path
from typing import List, Optional, Tuple

MAX_BYTES = 20 * 1024 * 1024
MD_TYPES = {".md", ".markdown", ".txt"}
HTML_TYPES = {".html", ".htm"}
JSON_TYPES = {".json"}
TYPES = MD_TYPES | HTML_TYPES | JSON_TYPES
SAVED_SUFFIX = ".airag.json"
DATA_ID = "airag-record"            # <script type="application/json" id="airag-record"> in exported pages
KEEP = ("query", "mode", "created", "model", "title", "article", "related", "language", "dates", "elapsed", "tags", "translations")
_SOURCE_LINE = re.compile(r"^\s*(\d+)\.\s+(?:\[(.*?)\]\((.*?)\)|(.+?))(?:\s+-\s+reliability\s+(\d+)/10)?\s*$")
_DISCLAIMER = re.compile(r"\n\*(?:Summary )?[Ww]ritten by AI with AIRAG[^\n]*\*\s*$")


class NotOpenable(ValueError):
    """The file isn't one AIRAG can open (shown to the reader)."""


def kind_of(name: str) -> str:
    from . import filereaders
    n = name.lower()
    ext = Path(n).suffix
    if n.endswith(SAVED_SUFFIX) or ext in JSON_TYPES:
        return "json"
    if ext in MD_TYPES:
        return "md"
    if ext in HTML_TYPES:
        return "html"
    if ext in filereaders.READERS or ext in filereaders.LEGACY:
        return "doc"
    raise NotOpenable("AIRAG can open text and Markdown, Word, PowerPoint, Excel, OpenDocument, PDF, RTF, CSV, JSON, "
                      "SQLite databases, saved AIRAG articles (.airag.json) and web pages.")


# ---------------------------------------------------------------- Markdown
def _front_matter(text: str) -> Tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end < 0:
        return {}, text
    meta = {}
    for line in text[3:end].splitlines():
        m = re.match(r"\s*([A-Za-z_][\w-]*)\s*:\s*(.*)$", line)
        if m:
            v = m.group(2).strip()
            if len(v) >= 2 and v[0] == v[-1] == '"':
                v = v[1:-1].replace('\\"', '"').replace("\\\\", "\\")
            meta[m.group(1).lower()] = v
    return meta, text[end + 4:].lstrip("\n")


def _sources(block: str) -> List[dict]:
    out = []
    for line in block.splitlines():
        m = _SOURCE_LINE.match(line)
        if not m:
            continue
        n, title, where, plain, trust = m.groups()
        where = (where or "").strip()
        s = {"n": int(n), "title": (title or plain or where or "").strip()}
        if where.startswith(("http://", "https://")):
            from urllib.parse import urlparse
            s["url"], s["domain"] = where, urlparse(where).netloc
        elif where:
            s["path"], s["local"], s["title"] = where, True, s["title"] or Path(where).name
        if trust:
            s["trust"] = int(trust)
        s["relevance"] = 5
        out.append(s)
    return out


def parse_markdown(text: str, name: str = "") -> dict:
    """AIRAG's saved Markdown (properties + article + "## Sources"), or any other Markdown file."""
    meta, body = _front_matter(text.replace("\r\n", "\n"))
    ours = meta.get("source", "").lower() == "airag"
    sources: List[dict] = []
    if ours:
        body = _DISCLAIMER.sub("", body.rstrip()) + "\n"
        cut = body.rfind("\n## Sources\n")
        if cut >= 0:
            sources = _sources(body[cut + 12:])
            body = body[:cut]
    body = body.strip()
    heading = re.search(r"^#\s+(.+)$", body, re.M)
    title = meta.get("title") or (heading.group(1).strip() if heading else "") or Path(name).stem or "Article"
    if not body:
        raise NotOpenable("The file is empty.")
    from . import tags
    return {"title": title, "query": meta.get("search") or title, "created": meta.get("created") or None,
            "model": meta.get("model") or "", "article": body, "article_sources": sources, "from_airag": ours,
            "tags": [t for t in tags.from_front_matter(text.replace("\r\n", "\n")) if t != tags.DEFAULT]}


# ---------------------------------------------------------------- saved JSON copies
def _clean_sources(items) -> List[dict]:
    out = []
    for s in items if isinstance(items, list) else []:
        if not isinstance(s, dict):
            continue
        keep = {k: s[k] for k in ("n", "title", "url", "domain", "site_name", "author", "published", "trust",
                                   "relevance", "path", "local", "summary", "kind") if k in s}
        if isinstance(keep.get("url"), str) and not keep["url"].startswith(("http://", "https://")):
            keep.pop("url")
        out.append(keep)
    return out


def _clean_images(items) -> List[dict]:
    out = []
    for im in items if isinstance(items, list) else []:
        if isinstance(im, dict) and isinstance(im.get("src"), str) and im["src"].startswith(("data:image/", "https://")):
            out.append({k: im[k] for k in ("src", "thumb", "alt", "page", "original_src") if isinstance(im.get(k), str)})
    return out


def parse_saved_json(text: str, trusted: bool = False) -> dict:
    try:
        rec = json.loads(text)
    except ValueError:
        raise NotOpenable("This JSON file isn't a saved AIRAG article.")
    if not isinstance(rec, dict) or not isinstance(rec.get("article"), str) or not (rec.get("query") or rec.get("title")):
        raise NotOpenable("This JSON file isn't a saved AIRAG article.")
    out = {k: rec[k] for k in KEEP if k in rec and isinstance(rec[k], (str, int, float, list, dict))}
    from . import tags
    out["tags"] = [t for t in tags.clean(out.get("tags") if isinstance(out.get("tags"), list) else []) if t != tags.DEFAULT]
    tr = out.get("translations")
    out["translations"] = {k: v for k, v in (tr.items() if isinstance(tr, dict) else [])
                           if isinstance(k, str) and re.fullmatch(r"[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})?", k)
                           and isinstance(v, str) and len(v) < 400_000}
    out["article_sources"] = _clean_sources(rec.get("article_sources") or rec.get("sources"))
    out["images"] = _clean_images(rec.get("images"))
    if trusted and isinstance(rec.get("interactive_html"), str):
        out["interactive_html"], out["interactive"] = rec["interactive_html"], rec.get("interactive")
    out["from_airag"] = True
    return out


# ---------------------------------------------------------------- web pages
def data_block(rec: dict) -> str:
    """The data copy that goes into an exported web page, so AIRAG can open it again exactly."""
    keep = {k: rec.get(k) for k in KEEP if rec.get(k) is not None}
    keep["article_sources"] = rec.get("article_sources") or []
    keep["airag_export"] = 1
    raw = json.dumps(keep, ensure_ascii=False).replace("</", "<\\/").replace("<!--", "<\\!--")
    return f'<script type="application/json" id="{DATA_ID}">{raw}</script>'


def parse_html(text: str, name: str = "") -> dict:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(text, "html.parser")
    tag = soup.find("script", id=DATA_ID, attrs={"type": "application/json"})
    if tag is not None and tag.string:
        rec = parse_saved_json(tag.string)
        imgs = [{"src": im["src"], "alt": im.get("alt", "")} for im in soup.select("main img[src^='data:image/']")][:16]
        rec["images"] = _clean_images(imgs)
        return rec
    # older exports and other web pages: take the readable text
    import trafilatura
    md = None
    for fmt in ("markdown", "txt"):
        try:
            md = trafilatura.extract(text, output_format=fmt, include_links=True, include_tables=True)
        except Exception:
            md = None
        if md:
            break
    if not md:
        raise NotOpenable("No readable text was found in this web page.")
    title = (soup.title.string or "").strip() if soup.title and soup.title.string else (Path(name).stem or "Web page")
    if not md.lstrip().startswith("#"):
        md = f"# {title}\n\n{md}"
    return {"title": title, "query": title, "article": md, "article_sources": [], "from_airag": False}


# ---------------------------------------------------------------- documents and data (Word, Excel, CSV, SQLite...)
def parse_document(name: str, data: bytes) -> dict:
    """Any other readable file: its text (tables as tables) becomes the article, its web links the sources.
    Nothing in the file runs; a database is only read."""
    from . import filereaders
    from urllib.parse import urlparse
    try:
        doc = filereaders.read(name, data)
    except filereaders.Unreadable as e:
        raise NotOpenable(str(e))
    if not doc.text.strip():
        raise NotOpenable("No readable text was found in this file.")
    title = doc.title or Path(name).stem or "File"
    body = doc.text.strip()
    if not body.startswith("# "):
        body = f"# {title}\n\n{body}"
    sources = [{"n": i, "title": urlparse(u).netloc or u, "url": u, "domain": urlparse(u).netloc}
               for i, u in enumerate(doc.links, 1)]
    return {"title": title, "query": title, "article": body, "article_sources": sources, "from_airag": False,
            "file_kind": doc.kind, "file_tables": doc.tables}


# ---------------------------------------------------------------- entry points
def parse(name: str, text: str = "", trusted: bool = False, data: Optional[bytes] = None) -> dict:
    """A file's record. Give `data` (the raw bytes) for anything that isn't plain text."""
    from . import filereaders
    kind = kind_of(name)
    size = len(data) if data is not None else len(text.encode("utf-8", "ignore"))
    if size > MAX_BYTES:
        raise NotOpenable("The file is too big to open (over 20 MB).")
    if kind == "doc":
        return parse_document(name, data if data is not None else text.encode("utf-8"))
    if data is not None:
        text = filereaders.decode(data)
    if kind == "md":
        return parse_markdown(text, name)
    if kind == "json":
        try:
            return parse_saved_json(text, trusted)
        except NotOpenable:
            if name.lower().endswith(SAVED_SUFFIX):
                raise
            return parse_document(name, text.encode("utf-8"))     # any other JSON: shown as data
    return parse_html(text, name)


def to_record(parsed: dict, name: str) -> dict:
    """A History entry for an opened file (outcome "article", no AI used)."""
    rec = dict(parsed)
    rec.update({"id": uuid.uuid4().hex[:12], "mode": rec.get("mode") or "article", "outcome": "article",
                "opened_file": Path(name).name, "status": "done"})
    rec.setdefault("created", dt.datetime.now().astimezone().isoformat(timespec="seconds"))
    rec["created"] = rec["created"] or dt.datetime.now().astimezone().isoformat(timespec="seconds")
    rec.setdefault("images", [])
    rec["sources"] = rec.get("article_sources") or []
    rec.pop("from_airag", None)
    return rec


def read_path(path: str) -> Tuple[str, bytes]:
    """Reads a file given by the operating system (Open with AIRAG). Only the types above, up to 20 MB."""
    p = Path(path)
    kind_of(p.name)
    if not p.is_file():
        raise NotOpenable("The file wasn't found.")
    if p.stat().st_size > MAX_BYTES:
        raise NotOpenable("The file is too big to open (over 20 MB).")
    return p.name, p.read_bytes()


def open_file(name: str, text: str = "", trusted: bool = False, data: Optional[bytes] = None) -> dict:
    from . import history
    rec = to_record(parse(name, text, trusted, data), name)
    history.save(rec)
    return rec


# files handed over by the operating system before the page asked for them (Windows "Open with")
inbox: List[str] = []
errors: List[str] = []


def queue(rid: str) -> None:
    inbox.append(rid)
    del inbox[:-10]


def take() -> dict:
    """The next file the page should show (or a message about one that couldn't be opened)."""
    if inbox:
        return {"id": inbox.pop(0)}
    if errors:
        return {"error": errors.pop(0)}
    return {}
