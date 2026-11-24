"""Readers for the file types AIRAG can read: they turn a file into Markdown text (tables as Markdown tables)
plus the web links found in it. Used by My library (indexing and search) and by Open with AIRAG.

Rules:
- Text and links only. Nothing in a file is ever run: no macros, formulas are read as their last saved value,
  SQL in a .db file is never executed (we only list its tables and read rows with our own SELECT),
  scripts in HTML are dropped.
- Pure Python (works on Android too) and capped everywhere: rows, cells, sheets, slides, bytes read from a zip
  (a small "zip bomb" can't fill the memory), characters of output.
- Office XML is read with simple patterns rather than an XML parser, so entity tricks (XXE, "billion laughs")
  have nothing to work on.

Add a type: write `_read_<kind>(data, name) -> Doc` and list its extensions in READERS.
"""
from __future__ import annotations

import csv
import html
import io
import json
import os
import re
import sqlite3
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

MAX_OUT = 2_000_000              # characters of text per file
MAX_ROWS = 2_000                 # rows per table (CSV, sheet, database table)
MAX_COLS = 40
MAX_CELL = 400                   # characters per cell
MAX_TABLES = 30                  # sheets / database tables
MAX_SLIDES = 300
MAX_ZIP_MEMBER = 40 * 1024 * 1024
MAX_ZIP_TOTAL = 120 * 1024 * 1024
MAX_LINKS = 60
_URL = re.compile(r"https?://[^\s<>\"'\])}|,]+", re.I)


class Unreadable(ValueError):
    """The file can't be read (message is shown to the reader)."""


@dataclass
class Doc:
    text: str                                  # Markdown
    title: str = ""
    kind: str = "text"                         # text / table / slides / database / document
    links: List[str] = field(default_factory=list)
    tables: int = 0
    truncated: bool = False


# ---------------------------------------------------------------- helpers
def decode(raw: bytes) -> str:
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        try:
            return raw.decode("utf-16")
        except UnicodeDecodeError:
            pass
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _cell(v) -> str:
    s = "" if v is None else str(v)
    s = s.replace("\r", " ").replace("\n", " ").replace("|", "\\|").strip()
    return s[:MAX_CELL] + ("…" if len(s) > MAX_CELL else "")


def md_table(rows: List[List], header: Optional[List] = None) -> str:
    """Rows as a Markdown table (the first row is the header when none is given)."""
    rows = [r[:MAX_COLS] for r in rows if any(str(x).strip() for x in r if x is not None)]
    if header is None:
        if not rows:
            return ""
        header, rows = rows[0], rows[1:]
    header = list(header)[:MAX_COLS]
    width = max([len(header)] + [len(r) for r in rows]) if rows or header else 0
    if not width:
        return ""
    header = [(_cell(h) or f"Column {i + 1}") for i, h in enumerate(header + [""] * (width - len(header)))]
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * width]
    for r in rows:
        r = [_cell(x) for x in r] + [""] * (width - len(r))
        out.append("| " + " | ".join(r) + " |")
    return "\n".join(out)


def links_in(text: str) -> List[str]:
    seen, out = set(), []
    for m in _URL.finditer(text):
        u = m.group(0).rstrip(".;:!?")
        if u not in seen:
            seen.add(u)
            out.append(u)
            if len(out) >= MAX_LINKS:
                break
    return out


def _x(s: str) -> str:
    """Text of an XML fragment (tags dropped, entities decoded)."""
    return html.unescape(re.sub(r"<[^>]+>", "", s))


def _zip_read(z: zipfile.ZipFile, name: str, budget: List[int]) -> str:
    info = z.getinfo(name)
    if info.file_size > MAX_ZIP_MEMBER:
        raise Unreadable("A part of this file is too big to read.")
    with z.open(info) as f:
        raw = f.read(MAX_ZIP_MEMBER + 1)
    if len(raw) > MAX_ZIP_MEMBER:
        raise Unreadable("A part of this file is too big to read.")
    budget[0] -= len(raw)
    if budget[0] < 0:
        raise Unreadable("This file unpacks to too much data to read.")
    return raw.decode("utf-8", "replace")


def _zip(data: bytes) -> zipfile.ZipFile:
    try:
        return zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise Unreadable("The file is damaged or isn't the type its name says.")


def _rels(z: zipfile.ZipFile, path: str, budget) -> Dict[str, Tuple[str, bool]]:
    """Relationship id -> (target, is an outside link)."""
    if path not in z.namelist():
        return {}
    out = {}
    for m in re.finditer(r"<Relationship\b([^>]*)/?>", _zip_read(z, path, budget)):
        a = dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))
        if "Id" in a:
            out[a["Id"]] = (html.unescape(a.get("Target", "")), a.get("TargetMode") == "External")
    return out


def _outside(rels: Dict[str, Tuple[str, bool]]) -> List[str]:
    return [t for t, ext in rels.values() if ext and re.match(r"https?://", t, re.I)]


# ---------------------------------------------------------------- plain text, CSV, JSON
def _read_text(data: bytes, name: str) -> Doc:
    t = decode(data)
    return Doc(t, kind="text", links=links_in(t))


def _read_csv(data: bytes, name: str) -> Doc:
    t = decode(data)
    sample = t[:20000]
    delim = "\t" if name.lower().endswith(".tsv") else None
    if delim is None:
        try:
            delim = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
        except csv.Error:
            delim = ","
    rows, truncated = [], False
    for i, r in enumerate(csv.reader(io.StringIO(t), delimiter=delim)):
        if i > MAX_ROWS:
            truncated = True
            break
        rows.append(r)
    table = md_table(rows)
    note = f"\n\n*Only the first {MAX_ROWS} rows are shown.*" if truncated else ""
    return Doc(table + note, kind="table", links=links_in(t), tables=1 if table else 0, truncated=truncated)


def _records(v):
    """A JSON value that is a list of objects (directly, or the biggest such list one level down)."""
    if isinstance(v, list) and v and all(isinstance(x, dict) for x in v[:50]):
        return v
    if isinstance(v, dict):
        best = None
        for x in v.values():
            if isinstance(x, list) and x and all(isinstance(y, dict) for y in x[:50]) and (best is None or len(x) > len(best)):
                best = x
        return best
    return None


def _read_json(data: bytes, name: str) -> Doc:
    t = decode(data)
    try:
        v = json.loads(t)
    except ValueError:
        return Doc("```\n" + t[:MAX_OUT] + "\n```", kind="text", links=links_in(t))
    recs = _records(v)
    if recs:
        cols: List[str] = []
        for r in recs[:200]:
            for k in r:
                if k not in cols and len(cols) < MAX_COLS:
                    cols.append(k)
        flat = lambda x: json.dumps(x, ensure_ascii=False) if isinstance(x, (dict, list)) else x
        rows = [[flat(r.get(c)) for c in cols] for r in recs[:MAX_ROWS]]
        note = f"\n\n*Only the first {MAX_ROWS} of {len(recs)} records are shown.*" if len(recs) > MAX_ROWS else ""
        return Doc(md_table(rows, cols) + note, kind="table", links=links_in(t), tables=1, truncated=bool(note))
    pretty = json.dumps(v, ensure_ascii=False, indent=2)
    return Doc("```json\n" + pretty[:MAX_OUT] + "\n```", kind="text", links=links_in(t), truncated=len(pretty) > MAX_OUT)


# ---------------------------------------------------------------- SQLite (read-only, our own SELECT only)
def _read_sqlite(data: bytes, name: str, path: Optional[Path] = None) -> Doc:
    from .sqlsafe import open_readonly, quote_ident
    if not data.startswith(b"SQLite format 3\x00"):
        raise Unreadable("This isn't an SQLite database.")
    tmp = None
    if path is None:                   # bytes only (picked or shared file): a private temporary copy
        fd, tmp = tempfile.mkstemp(suffix=".db")
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        path = Path(tmp)
    parts, links, n = [], [], 0
    try:
        c = open_readonly(path)
        try:
            names = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view') "
                                              "AND name NOT LIKE 'sqlite\\_%' ESCAPE '\\' ORDER BY name LIMIT ?", (MAX_TABLES,))]
            for tname in names:
                try:
                    cur = c.execute(f"SELECT * FROM {quote_ident(tname)} LIMIT ?", (MAX_ROWS + 1,))  # noqa: sql (quoted name)
                    cols = [d[0] for d in cur.description or []]
                    rows = [[(f"<{len(v)} bytes>" if isinstance(v, (bytes, bytearray)) else v) for v in r] for r in cur.fetchall()]
                except sqlite3.DatabaseError:
                    continue
                more = len(rows) > MAX_ROWS
                body = md_table(rows[:MAX_ROWS], cols) or "*(empty)*"
                parts.append(f"## {tname}\n\n{body}" + (f"\n\n*Only the first {MAX_ROWS} rows are shown.*" if more else ""))
                n += 1
                links += links_in(body)
        finally:
            c.close()
    except sqlite3.DatabaseError:
        raise Unreadable("The database couldn't be read.")
    finally:
        if tmp:
            try:
                os.unlink(tmp)
            except OSError:
                pass
    return Doc("\n\n".join(parts) or "*This database has no tables.*", kind="database", links=links[:MAX_LINKS], tables=n)


# ---------------------------------------------------------------- Word (.docx)
def _docx_par(p: str, rels) -> str:
    style = re.search(r'<w:pStyle w:val="([^"]+)"', p)
    out = []
    for m in re.finditer(r'<w:hyperlink\b([^>]*)>(.*?)</w:hyperlink>|<w:t(?:\s[^>]*)?>(.*?)</w:t>|<w:tab/>|<w:br/>', p, re.S):
        if m.group(2) is not None:
            txt = "".join(html.unescape(x) for x in re.findall(r"<w:t(?:\s[^>]*)?>(.*?)</w:t>", m.group(2), re.S))
            rid = re.search(r'r:id="([^"]+)"', m.group(1) or "")
            target = rels.get(rid.group(1), ("", False))[0] if rid else ""
            out.append(f"[{txt}]({target})" if target.startswith(("http://", "https://")) and txt else txt)
        elif m.group(3) is not None:
            out.append(html.unescape(m.group(3)))
        else:
            out.append(" ")
    text = "".join(out).strip()
    if not text:
        return ""
    h = re.match(r"(?i)heading\s*(\d)|title", style.group(1)) if style else None
    if h:
        return "#" * min(6, int(h.group(1) or 1) + (1 if h.group(1) else 0)) + " " + text
    if style and re.match(r"(?i)list", style.group(1)) or "<w:numPr>" in p:
        return "- " + text
    return text


def _read_docx(data: bytes, name: str) -> Doc:
    budget = [MAX_ZIP_TOTAL]
    with _zip(data) as z:
        if "word/document.xml" not in z.namelist():
            raise Unreadable("This Word file has no text.")
        xml = _zip_read(z, "word/document.xml", budget)
        rels = _rels(z, "word/_rels/document.xml.rels", budget)
    body = xml.split("<w:body>", 1)[-1]
    parts, tables = [], 0
    for m in re.finditer(r"<w:tbl>(.*?)</w:tbl>|<w:p\b[^>]*?(?:/>|>(.*?)</w:p>)", body, re.S):
        if m.group(1) is not None:
            rows = [[_x(c) for c in re.findall(r"<w:tc>(.*?)</w:tc>", row, re.S)]
                    for row in re.findall(r"<w:tr\b[^>]*>(.*?)</w:tr>", m.group(1), re.S)]
            t = md_table(rows)
            if t:
                parts.append(t)
                tables += 1
        elif m.group(2):
            line = _docx_par(m.group(2), rels)
            if line:
                parts.append(line)
    text = "\n\n".join(parts)
    return Doc(text, kind="document", links=(_outside(rels) + links_in(text))[:MAX_LINKS], tables=tables)


# ---------------------------------------------------------------- Excel (.xlsx)
def _col(ref: str) -> int:
    n = 0
    for ch in re.match(r"[A-Z]*", ref).group(0):
        n = n * 26 + ord(ch) - 64
    return max(0, n - 1)


def _read_xlsx(data: bytes, name: str) -> Doc:
    budget = [MAX_ZIP_TOTAL]
    with _zip(data) as z:
        names = set(z.namelist())
        shared = []
        if "xl/sharedStrings.xml" in names:
            for si in re.findall(r"<si>(.*?)</si>", _zip_read(z, "xl/sharedStrings.xml", budget), re.S):
                shared.append("".join(html.unescape(t) for t in re.findall(r"<t(?:\s[^>]*)?>(.*?)</t>", si, re.S)))
        wb = _zip_read(z, "xl/workbook.xml", budget) if "xl/workbook.xml" in names else ""
        wrels = _rels(z, "xl/_rels/workbook.xml.rels", budget)
        sheets = []
        for m in re.finditer(r"<sheet\b([^>]*)/?>", wb):
            a = dict(re.findall(r'([\w:]+)="([^"]*)"', m.group(1)))
            target = wrels.get(a.get("r:id", ""), ("", False))[0]
            path = target.lstrip("/") if target.startswith("/") else "xl/" + target
            if path in names:
                sheets.append((html.unescape(a.get("name", "Sheet")), path))
        if not sheets:
            sheets = [(Path(n).stem, n) for n in sorted(names) if re.match(r"xl/worksheets/sheet\d+\.xml$", n)]
        parts, links, n = [], [], 0
        for sname, path in sheets[:MAX_TABLES]:
            xml = _zip_read(z, path, budget)
            grid: List[List[str]] = []
            truncated = False
            for i, row in enumerate(re.finditer(r"<row\b[^>]*>(.*?)</row>", xml, re.S)):
                if i >= MAX_ROWS:
                    truncated = True
                    break
                cells: Dict[int, str] = {}
                for c in re.finditer(r"<c\b([^>]*?)(?:/>|>(.*?)</c>)", row.group(1), re.S):
                    a = dict(re.findall(r'(\w+)="([^"]*)"', c.group(1)))
                    inner = c.group(2) or ""
                    v = re.search(r"<v>(.*?)</v>", inner, re.S)
                    typ = a.get("t", "")
                    if typ == "s" and v:
                        try:
                            val = shared[int(v.group(1))]
                        except (ValueError, IndexError):
                            val = ""
                    elif typ == "inlineStr":
                        val = _x(inner)
                    elif typ == "b" and v:
                        val = "TRUE" if v.group(1) == "1" else "FALSE"
                    else:
                        f = re.search(r"<f>(.*?)</f>", inner, re.S)
                        val = html.unescape(v.group(1)) if v and v.group(1) else ("=" + html.unescape(f.group(1)) if f else "")
                    col = _col(a.get("r", "")) if a.get("r") else len(cells)
                    if col < MAX_COLS:
                        cells[col] = val
                if cells:
                    grid.append([cells.get(k, "") for k in range(max(cells) + 1)])
            srels = _rels(z, path.rsplit("/", 1)[0] + "/_rels/" + path.rsplit("/", 1)[1] + ".rels", budget)
            links += _outside(srels)
            table = md_table(grid)
            if table:
                parts.append(f"## {sname}\n\n{table}" + (f"\n\n*Only the first {MAX_ROWS} rows are shown.*" if truncated else ""))
                n += 1
    text = "\n\n".join(parts) or "*This workbook is empty.*"
    return Doc(text, kind="table", links=(links + links_in(text))[:MAX_LINKS], tables=n)


# ---------------------------------------------------------------- PowerPoint (.pptx)
def _paras(xml: str) -> List[str]:
    return [t for t in (_x(re.sub(r"<a:br/>", " ", p)).strip() for p in re.findall(r"<a:p>(.*?)</a:p>", xml, re.S)) if t]


def _read_pptx(data: bytes, name: str) -> Doc:
    budget = [MAX_ZIP_TOTAL]
    with _zip(data) as z:
        names = set(z.namelist())
        slides = sorted((n for n in names if re.match(r"ppt/slides/slide\d+\.xml$", n)), key=lambda s: int(re.search(r"(\d+)", s.rsplit("/", 1)[1]).group(1)))
        parts, links = [], []
        for i, s in enumerate(slides[:MAX_SLIDES], 1):
            paras = _paras(_zip_read(z, s, budget))
            num = re.search(r"(\d+)", s.rsplit("/", 1)[1]).group(1)
            note_path = f"ppt/notesSlides/notesSlide{num}.xml"
            notes = [p for p in _paras(_zip_read(z, note_path, budget)) if not p.isdigit()] if note_path in names else []
            links += _outside(_rels(z, f"ppt/slides/_rels/slide{num}.xml.rels", budget))
            if not paras and not notes:
                continue
            head = paras[0] if paras else f"Slide {i}"
            block = [f"## {i}. {head}"] + [f"- {p}" for p in paras[1:]]
            if notes:
                block.append("*Notes:* " + " ".join(notes))
            parts.append("\n".join(block))
    text = "\n\n".join(parts) or "*This presentation has no text.*"
    return Doc(text, kind="slides", links=(links + links_in(text))[:MAX_LINKS])


# ---------------------------------------------------------------- OpenDocument (.odt, .ods, .odp)
def _odf_grid(table_xml: str) -> List[List[str]]:
    grid = []
    for row in re.findall(r"<table:table-row\b[^>]*>(.*?)</table:table-row>", table_xml, re.S)[:MAX_ROWS]:
        cells: List[str] = []
        for c in re.finditer(r"<table:(?:covered-)?table-cell\b([^>]*?)(?:/>|>(.*?)</table:(?:covered-)?table-cell>)", row, re.S):
            rep = re.search(r'number-columns-repeated="(\d+)"', c.group(1))
            val = " ".join(_x(p) for p in re.findall(r"<text:p\b[^>]*>(.*?)</text:p>", c.group(2) or "", re.S))
            cells += [val] * min(int(rep.group(1)) if rep else 1, MAX_COLS)
            if len(cells) >= MAX_COLS:
                break
        while cells and not cells[-1]:
            cells.pop()
        if cells:
            grid.append(cells)
    return grid


def _read_odf(data: bytes, name: str) -> Doc:
    budget = [MAX_ZIP_TOTAL]
    with _zip(data) as z:
        if "content.xml" not in z.namelist():
            raise Unreadable("This file has no text.")
        xml = _zip_read(z, "content.xml", budget)
    ext = Path(name).suffix.lower()
    links = [html.unescape(u) for u in re.findall(r'xlink:href="(https?://[^"]+)"', xml)]
    if ext == ".ods":
        parts, n = [], 0
        for m in re.finditer(r'<table:table\b([^>]*)>(.*?)</table:table>', xml, re.S):
            tname = html.unescape((re.search(r'table:name="([^"]*)"', m.group(1)) or [None, "Sheet"])[1])
            t = md_table(_odf_grid(m.group(2)))
            if t:
                parts.append(f"## {tname}\n\n{t}")
                n += 1
            if n >= MAX_TABLES:
                break
        text = "\n\n".join(parts) or "*This spreadsheet is empty.*"
        return Doc(text, kind="table", links=(links + links_in(text))[:MAX_LINKS], tables=n)
    if ext == ".odp":
        parts = []
        txt = lambda s: [t for t in (_x(p).strip() for p in re.findall(r"<text:(?:p|h)\b[^>]*>(.*?)</text:(?:p|h)>", s, re.S))
                         if t and t not in ("<number>", "<date/time>", "<footer>", "<header>")]
        for i, page in enumerate(re.findall(r"<draw:page\b[^>]*>(.*?)</draw:page>", xml, re.S)[:MAX_SLIDES], 1):
            notes = " ".join(txt(" ".join(re.findall(r"<presentation:notes\b[^>]*>(.*?)</presentation:notes>", page, re.S))))
            paras = txt(re.sub(r"<presentation:notes\b.*?</presentation:notes>", "", page, flags=re.S))
            if paras or notes:
                block = [f"## {i}. {paras[0] if paras else f'Slide {i}'}"] + [f"- {p}" for p in paras[1:]]
                if notes:
                    block.append("*Notes:* " + notes)
                parts.append("\n".join(block))
        text = "\n\n".join(parts) or "*This presentation has no text.*"
        return Doc(text, kind="slides", links=(links + links_in(text))[:MAX_LINKS])
    parts, tables = [], 0
    for m in re.finditer(r'<table:table\b[^>]*>(.*?)</table:table>|<text:h\b([^>]*)>(.*?)</text:h>|<text:p\b[^>]*>(.*?)</text:p>', xml, re.S):
        if m.group(1) is not None:
            t = md_table(_odf_grid(m.group(1)))
            if t:
                parts.append(t)
                tables += 1
        elif m.group(3) is not None:
            lvl = re.search(r'outline-level="(\d)"', m.group(2))
            t = _x(m.group(3)).strip()
            if t:
                parts.append("#" * min(6, int(lvl.group(1)) + 1 if lvl else 2) + " " + t)
        else:
            t = _x(m.group(4)).strip()
            if t:
                parts.append(t)
    text = "\n\n".join(parts)
    return Doc(text, kind="document", links=(links + links_in(text))[:MAX_LINKS], tables=tables)


# ---------------------------------------------------------------- PDF, HTML, RTF
def _read_pdf(data: bytes, name: str) -> Doc:
    from pypdf import PdfReader
    try:
        reader = PdfReader(io.BytesIO(data))
        text = "\n\n".join((pg.extract_text() or "") for pg in reader.pages[:400])
    except Exception:
        raise Unreadable("The PDF couldn't be read.")
    return Doc(text, kind="document", links=links_in(text))


def _read_html(data: bytes, name: str) -> Doc:
    from bs4 import BeautifulSoup
    t = decode(data)
    try:
        soup = BeautifulSoup(t, "lxml")
    except Exception:
        soup = BeautifulSoup(t, "html.parser")
    for x in soup(["script", "style", "noscript", "template", "iframe", "object"]):
        x.decompose()
    links = [a["href"] for a in soup.find_all("a", href=True) if re.match(r"https?://", a["href"], re.I)][:MAX_LINKS]
    title = soup.title.get_text(strip=True) if soup.title else ""
    return Doc(soup.get_text("\n", strip=True), title=title, kind="document", links=links)


def _read_rtf(data: bytes, name: str) -> Doc:
    t = decode(data)
    t = re.sub(r"\{\\\*[^{}]*\}", "", t)                          # ignorable destinations
    t = re.sub(r"\{\\(?:fonttbl|colortbl|stylesheet|info|pict)[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", "", t)
    t = re.sub(r"\\'([0-9a-f]{2})", lambda m: bytes([int(m.group(1), 16)]).decode("cp1252", "replace"), t)
    t = re.sub(r"\\u(-?\d+)\??", lambda m: chr(int(m.group(1)) % 65536), t)
    t = re.sub(r"\\(?:par|line)\b ?", "\n", t)
    t = re.sub(r"\\[a-z]+-?\d* ?|[{}]", "", t)
    t = re.sub(r"\n{3,}", "\n\n", t).strip()
    return Doc(t, kind="document", links=links_in(t))


# ---------------------------------------------------------------- registry
READERS: Dict[str, Callable[[bytes, str], Doc]] = {
    **{e: _read_text for e in (".md", ".markdown", ".txt", ".text", ".rst", ".org", ".tex", ".log")},
    ".csv": _read_csv, ".tsv": _read_csv,
    ".json": _read_json,
    ".db": _read_sqlite, ".sqlite": _read_sqlite, ".sqlite3": _read_sqlite,
    ".docx": _read_docx, ".xlsx": _read_xlsx, ".xlsm": _read_xlsx, ".pptx": _read_pptx,
    ".odt": _read_odf, ".ods": _read_odf, ".odp": _read_odf,
    ".pdf": _read_pdf, ".html": _read_html, ".htm": _read_html, ".rtf": _read_rtf,
}
# older binary Office formats: no pure-Python reader; say so plainly instead of showing garbage
LEGACY = {".doc": ".docx", ".xls": ".xlsx", ".ppt": ".pptx"}
DATA_TYPES = {".csv", ".tsv", ".json", ".db", ".sqlite", ".sqlite3", ".xlsx", ".xlsm", ".ods"}
DOCUMENT_TYPES = {".docx", ".pptx", ".odt", ".odp", ".pdf", ".rtf"}


def supported(name: str) -> bool:
    return Path(name).suffix.lower() in READERS


def read(name: str, data: bytes, path: Optional[Path] = None) -> Doc:
    """Reads a file's bytes (path given for SQLite files on disk, so they aren't copied)."""
    ext = Path(name).suffix.lower()
    if ext in LEGACY:
        raise Unreadable(f"Older {ext} files can't be read. Save it as {LEGACY[ext]} and try again.")
    fn = READERS.get(ext)
    if not fn:
        raise Unreadable(f"AIRAG can't read {ext or 'these'} files.")
    try:
        doc = _read_sqlite(data, name, path) if fn is _read_sqlite else fn(data, name)
    except (Unreadable, MemoryError):
        raise
    except (zipfile.BadZipFile, KeyError, ValueError, UnicodeError) as e:
        raise Unreadable("The file is damaged or isn't the type its name says.") from e
    doc.links = list(dict.fromkeys(doc.links))[:MAX_LINKS]
    if len(doc.text) > MAX_OUT:
        doc.text, doc.truncated = doc.text[:MAX_OUT], True
    doc.title = doc.title or Path(name).stem
    return doc


def read_path(p: Path, max_bytes: int) -> Doc:
    if p.stat().st_size > max_bytes:
        raise Unreadable("The file is too big.")
    ext = p.suffix.lower()
    if ext in (".db", ".sqlite", ".sqlite3"):
        with open(p, "rb") as f:
            head = f.read(16)
        return read(p.name, head, p)
    return read(p.name, p.read_bytes())
