"""Retrieve & Get - a local library of your own files (notes, Obsidian vaults, PDFs, docs).

Files are split into chunks and indexed with SQLite FTS5 (BM25 ranking). The
index is incremental: only new or changed files are re-read. Nothing leaves
your computer except the excerpts sent to the AI model you selected.
"""
from __future__ import annotations

import logging
import os
import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .paths import LIBRARY_DB

log = logging.getLogger("airag.library")

SKIP_DIRS = {".git", ".obsidian", ".trash", "node_modules", "__pycache__", ".venv", "venv", ".idea", ".vscode",
             "$recycle.bin", "system volume information", ".cache"}
CHUNK = 1100
MAX_TEXT = 2_000_000
_CJK = re.compile(r"([぀-ヿ㐀-䶿一-鿿가-힯豈-﫿])")
_lock = threading.RLock()


def cjk_space(text: str) -> str:
    """FTS5's unicode61 tokenizer needs spaces; put them around CJK characters."""
    return _CJK.sub(r" \1 ", text)


# extraction
def _read_text(p: Path) -> str:
    raw = p.read_bytes()[: MAX_TEXT * 2]
    for enc in ("utf-8-sig", "utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def extract(p: Path) -> str:
    """The file's text as Markdown (tables as Markdown tables), from the readers in filereaders.py."""
    from . import filereaders
    if p.suffix.lower() not in filereaders.READERS:
        return _read_text(p)
    return filereaders.read_path(p, MAX_TEXT * 50).text


def title_of(p: Path, text: str) -> str:
    if p.suffix.lower() in (".md", ".markdown"):
        m = re.search(r"^#\s+(.+)$", text, re.M)
        if m:
            return m.group(1).strip()[:200]
    return p.stem


def chunks_of(text: str) -> List[str]:
    text = re.sub(r"^---\n.*?\n---\n", "", text, count=1, flags=re.S)  # YAML front matter
    paras = [x.strip() for x in re.split(r"\n\s*\n", text) if x.strip()]
    out, cur = [], ""
    for para in paras:
        while len(para) > CHUNK * 1.6:
            cut = para.rfind(". ", 0, CHUNK) + 1 or CHUNK
            if cur:
                out.append(cur)
                cur = ""
            out.append(para[:cut].strip())
            para = para[cut:].strip()
        if len(cur) + len(para) > CHUNK and cur:
            out.append(cur)
            cur = ""
        cur = (cur + "\n\n" + para).strip()
    if cur:
        out.append(cur)
    return out


# index
class Library:
    def __init__(self, db_path: Path = LIBRARY_DB):
        self.db_path = db_path
        self.fts = True   # False when this SQLite build has no FTS5 (some Android builds)

    def _conn(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(str(self.db_path), timeout=30, check_same_thread=False)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=NORMAL")
        c.executescript("""
            CREATE TABLE IF NOT EXISTS files(id INTEGER PRIMARY KEY, path TEXT UNIQUE, root TEXT, title TEXT,
                mtime REAL, size INTEGER, chunks INTEGER DEFAULT 0, error TEXT);
            CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
        """)
        cols = {r[1] for r in c.execute("PRAGMA table_info(files)")}
        if "tags" not in cols:      # 0.4.1: tags; Markdown files are read again once to pick theirs up
            c.execute("ALTER TABLE files ADD COLUMN tags TEXT")
            c.execute("UPDATE files SET mtime = 0 WHERE lower(path) LIKE '%.md' OR lower(path) LIKE '%.markdown'")
            c.commit()
        try:
            c.execute("CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING fts5(text, title, file_id UNINDEXED, "
                      "ord UNINDEXED, tokenize='unicode61 remove_diacritics 2')")
            self.fts = True
        except sqlite3.OperationalError:
            self.fts = False
            c.execute("CREATE TABLE IF NOT EXISTS chunks(text TEXT, title TEXT, file_id INTEGER, ord INTEGER)")
            c.execute("CREATE INDEX IF NOT EXISTS chunks_file ON chunks(file_id)")
        row = c.execute("SELECT sql FROM sqlite_master WHERE name='chunks'").fetchone()
        self.fts = bool(row and "fts5" in (row[0] or "").lower())
        return c

    # ---- sync
    def sync(self, folders: List[str], extensions: List[str], max_mb: float = 25,
             progress: Optional[Callable[[int, int, str], None]] = None,
             cancelled: Callable[[], bool] = lambda: False) -> dict:
        exts = {e.strip().lower() if e.strip().startswith(".") else "." + e.strip().lower() for e in extensions if e.strip()}
        roots = [str(Path(f).expanduser()) for f in folders if f and Path(f).expanduser().is_dir()]
        protected = _protected_roots()
        files: Dict[str, tuple] = {}
        for root in roots:
            for dirpath, dirnames, filenames in os.walk(root):  # doesn't follow symlinked folders
                here = Path(dirpath).resolve()
                if any(here == r or r in here.parents for r in protected):
                    dirnames[:] = []
                    continue
                dirnames[:] = [d for d in dirnames if d.lower() not in SKIP_DIRS and not d.startswith(".")]
                for fn in filenames:
                    p = Path(dirpath) / fn
                    if p.suffix.lower() not in exts or fn.startswith("~$") or is_secret_file(p) or p.is_symlink():
                        continue
                    try:
                        st = p.stat()
                    except OSError:
                        continue
                    if st.st_size > max_mb * 1024 * 1024 or st.st_size == 0:
                        continue
                    files[str(p)] = (root, st.st_mtime, st.st_size)
        added = updated = removed = failed = 0
        with _lock:
            c = self._conn()
            try:
                known = {r["path"]: (r["id"], r["mtime"], r["size"]) for r in c.execute("SELECT id, path, mtime, size FROM files")}
                for path, (fid, _, _) in known.items():
                    if path not in files:
                        c.execute("DELETE FROM chunks WHERE file_id=?", (fid,))
                        c.execute("DELETE FROM files WHERE id=?", (fid,))
                        removed += 1
                todo = [p for p, (root, mt, sz) in files.items()
                        if p not in known or abs(known[p][1] - mt) > 1e-6 or known[p][2] != sz]
                for i, path in enumerate(todo):
                    if cancelled():
                        break
                    if progress:
                        progress(i, len(todo), path)
                    root, mt, sz = files[path]
                    p = Path(path)
                    file_tags = ""
                    try:
                        text = extract(p)[:MAX_TEXT]
                        err = None
                        if p.suffix.lower() in (".md", ".markdown"):
                            from .tags import from_front_matter, DEFAULT
                            file_tags = ",".join(t for t in from_front_matter(text) if t != DEFAULT)
                    except Exception as e:
                        text, err = "", f"{type(e).__name__}: {e}"[:200]
                        failed += 1
                    title = title_of(p, text)
                    parts = chunks_of(text) if text else []
                    if path in known:
                        fid = known[path][0]
                        c.execute("DELETE FROM chunks WHERE file_id=?", (fid,))
                        c.execute("UPDATE files SET root=?, title=?, mtime=?, size=?, chunks=?, error=?, tags=? WHERE id=?",
                                  (root, title, mt, sz, len(parts), err, file_tags, fid))
                        updated += 1
                    else:
                        cur = c.execute("INSERT INTO files(path, root, title, mtime, size, chunks, error, tags) VALUES(?,?,?,?,?,?,?,?)",
                                        (path, root, title, mt, sz, len(parts), err, file_tags))
                        fid = cur.lastrowid
                        added += 1
                    c.executemany("INSERT INTO chunks(text, title, file_id, ord) VALUES(?,?,?,?)",
                                  [(cjk_space(t), cjk_space(title), fid, n) for n, t in enumerate(parts)])
                    if i % 40 == 39:
                        c.commit()
                c.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('last_sync', ?)", (str(time.time()),))
                c.commit()
            finally:
                c.close()
        return {"added": added, "updated": updated, "removed": removed, "failed": failed, **self.stats()}

    # ---- search
    @staticmethod
    def _match_expr(queries: List[str]) -> str:
        """FTS search words: only letters/digits (no quotes, operators or SQL can get through), each one quoted."""
        words: List[str] = []
        for q in queries:
            for w in re.findall(r"\w+", cjk_space(q.lower())):
                if (len(w) > 1 or _CJK.match(w)) and w not in words:
                    words.append(w)
        return " OR ".join(f'"{w}"' for w in words[:40])

    def search(self, queries: List[str], limit: int = 6, per_file_chars: int = 3500) -> List[dict]:
        expr = self._match_expr(queries)
        if not expr or not self.db_path.exists():
            return []
        with _lock:
            c = self._conn()
            try:
                if self.fts:
                    rows = c.execute(
                        "SELECT file_id, ord, text, bm25(chunks, 1.0, 2.0) AS score FROM chunks WHERE chunks MATCH ? "
                        "ORDER BY score LIMIT 400", (expr,)).fetchall()
                else:
                    rows = self._plain_search(c, expr)
                by_file: Dict[int, dict] = {}
                for r in rows:
                    f = by_file.setdefault(int(r["file_id"]), {"score": 0.0, "hits": []})
                    f["score"] += -float(r["score"])  # bm25: lower is better
                    f["hits"].append((int(r["ord"]), r["text"]))
                # files whose tags appear in the question are read first (with their opening parts if no word matched)
                from .tags import matches
                question = " ".join(queries)
                for r in c.execute("SELECT id, tags FROM files WHERE tags IS NOT NULL AND tags != ''"):
                    if matches(r["tags"].split(","), question):
                        f = by_file.setdefault(int(r["id"]), {"score": 0.0, "hits": []})
                        f["score"] += 1e6
                        f["tagged"] = True
                        if not f["hits"]:
                            f["hits"] = [(int(x["ord"]), x["text"]) for x in
                                         c.execute("SELECT ord, text FROM chunks WHERE file_id=? ORDER BY ord LIMIT 3", (r["id"],))]
                best = sorted(by_file.items(), key=lambda kv: -kv[1]["score"])[:limit]
                out = []
                for fid, f in best:
                    meta = c.execute("SELECT * FROM files WHERE id=?", (fid,)).fetchone()
                    if not meta:
                        continue
                    hits = sorted(f["hits"][:6])  # top chunks, in document order
                    excerpt, used = [], 0
                    for _, t in hits:
                        t = _CJK_UNSPACE.sub(r"\1", t)
                        if used + len(t) > per_file_chars:
                            break
                        excerpt.append(t)
                        used += len(t)
                    out.append({"file_id": fid, "path": meta["path"], "root": meta["root"], "title": meta["title"],
                                "score": round(f["score"] - (1e6 if f.get("tagged") else 0), 3), "tagged": bool(f.get("tagged")),
                                "tags": [t for t in (meta["tags"] or "").split(",") if t],
                                "excerpt": "\n[…]\n".join(excerpt), "mtime": meta["mtime"]})
                return out
            finally:
                c.close()

    @staticmethod
    def _plain_search(c, expr: str) -> list:
        """Simple keyword scoring for SQLite builds without FTS5."""
        words = [w.strip('"') for w in expr.split(" OR ")][:12]
        if not words:
            return []
        from .sqlsafe import like_escape
        cond = " OR ".join("lower(text) LIKE ? ESCAPE '\\'" for _ in words)     # fixed text; the words are parameters
        rows = c.execute(f"SELECT file_id, ord, text, title FROM chunks WHERE {cond} LIMIT 2000",  # noqa: sql (fixed text)
                         [f"%{like_escape(w)}%" for w in words]).fetchall()
        scored = []
        for r in rows:
            low = (r["text"] + " " + (r["title"] or "")).lower()
            score = sum(low.count(w) for w in words) + 2 * sum(1 for w in words if w in low)
            scored.append({"file_id": r["file_id"], "ord": r["ord"], "text": r["text"], "score": -float(score)})
        return sorted(scored, key=lambda x: x["score"])[:400]

    # ---- misc
    def get_file(self, fid: int) -> Optional[dict]:
        if not self.db_path.exists():
            return None
        with _lock:
            c = self._conn()
            try:
                r = c.execute("SELECT * FROM files WHERE id=?", (fid,)).fetchone()
                return dict(r) if r else None
            finally:
                c.close()

    def stats(self) -> dict:
        if not self.db_path.exists():
            return {"files": 0, "chunks": 0, "bytes": 0, "last_sync": None, "errors": 0}
        with _lock:
            c = self._conn()
            try:
                files = c.execute("SELECT COUNT(*), COALESCE(SUM(chunks),0), SUM(error IS NOT NULL) FROM files").fetchone()
                last = c.execute("SELECT value FROM meta WHERE key='last_sync'").fetchone()
                per_root = [dict(r) for r in c.execute("SELECT root, COUNT(*) AS files FROM files GROUP BY root")]
            finally:
                c.close()
        size = sum(p.stat().st_size for p in self.db_path.parent.glob(self.db_path.name + "*") if p.exists())
        return {"files": files[0], "chunks": files[1], "errors": files[2] or 0, "bytes": size,
                "last_sync": float(last[0]) if last else None, "roots": per_root}

    def last_sync(self) -> float:
        s = self.stats().get("last_sync")
        return s or 0.0

    def clear(self) -> None:
        with _lock:
            for p in self.db_path.parent.glob(self.db_path.name + "*"):
                try:
                    p.unlink()
                except OSError:
                    pass


_CJK_UNSPACE = re.compile(r" ([぀-ヿ㐀-䶿一-鿿가-힯豈-﫿]) ")
LIBRARY = Library()


# ---- what AIRAG may read
# Never indexed or served, even inside a folder the user added: AIRAG's own data,
# and files that typically hold passwords, keys or certificates.
SECRET_NAMES = {"settings.json", ".env", ".envrc", ".netrc", ".npmrc", ".pypirc", ".git-credentials", "credentials",
                "credentials.json", "secrets.json", "secrets.yaml", "secrets.yml", "id_rsa", "id_ed25519", "id_ecdsa",
                "id_dsa", "known_hosts", "authorized_keys", "wallet.dat", "keystore.json", "service-account.json"}
SECRET_EXTS = {".pem", ".key", ".p12", ".pfx", ".jks", ".keystore", ".kdbx", ".kdb", ".1pux", ".opvault", ".agilekeychain",
               ".gpg", ".asc", ".ppk", ".ovpn", ".crt", ".cer", ".der", ".sqlite", ".db"}
SECRET_WORDS = {"password", "passwords", "passwd", "credential", "credentials", "secrets", "apikey", "apikeys",
                "privatekey", "seedphrase", "mnemonic", "2fa", "backupcodes", "recoverycodes"}


def _protected_roots() -> List[Path]:
    from . import paths
    roots = [paths.CONFIG_DIR, paths.LOCAL_DIR, paths.APP_DIR if paths.FROZEN else None]
    out = []
    for r in roots:
        try:
            if r:
                out.append(Path(r).resolve())
        except OSError:
            pass
    return out


def is_secret_file(p: Path) -> bool:
    name = p.name.lower()
    if name.endswith(".airag.json"):   # AIRAG's own copy of a saved article (the .md next to it is indexed)
        return True
    if name in SECRET_NAMES or p.suffix.lower() in SECRET_EXTS or name.startswith(".env"):
        return True
    words = re.split(r"[^a-z0-9]+", p.stem.lower())
    joined = {a + b for a, b in zip(words, words[1:])}   # "api-key", "recovery codes"
    return bool(SECRET_WORDS & (set(words) | joined))


def allowed_file(path, settings: dict) -> bool:
    """True only for a real file, of an allowed type, inside a library folder, outside AIRAG's own
    folders and not a likely secrets file. Symlinks and '..' are resolved before checking."""
    try:
        rp = Path(path).expanduser().resolve()
    except (OSError, RuntimeError):
        return False
    args = settings_args(settings)
    exts = {e.strip().lower() if e.strip().startswith(".") else "." + e.strip().lower()
            for e in args["extensions"] if e.strip()}
    if rp.suffix.lower() not in exts or is_secret_file(rp):
        return False
    if any(rp == r or r in rp.parents for r in _protected_roots()):
        return False
    roots = []
    for f in args["folders"]:
        try:
            roots.append(Path(f).expanduser().resolve())
        except (OSError, RuntimeError):
            pass
    if not any(r in rp.parents for r in roots):
        return False
    return rp.is_file()


def settings_args(settings: dict) -> dict:
    lib = settings.get("library", {})
    folders = list(lib.get("folders") or [])
    try:   # My library (saved articles, imported files) is always searched when it exists
        from .mylibrary import folder
        mine = folder(settings)
        if mine.is_dir() and str(mine) not in folders:
            folders.append(str(mine))
    except Exception:
        pass
    return {"folders": folders,
            "extensions": [e for e in str(lib.get("extensions", "")).split(",")],
            "max_mb": float(lib.get("max_file_mb") or 25)}
