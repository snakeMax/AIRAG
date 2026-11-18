"""Safe SQL helpers. Rules for all SQL in AIRAG:

1. Values always go in as bound parameters (`?`), never pasted into the SQL text.
2. The SQL text itself is always written by us. Text from the AI, web pages or files is never run as SQL,
   and no AI agent or tool can send SQL (there is no SQL tool, by design).
3. Names that come from a file (tables and columns of a library .db file) are quoted with `quote_ident`,
   and those files are opened with `open_readonly`: read-only, SELECT-only, nothing attached or loaded.
4. Search words for LIKE are escaped with `like_escape`; FTS search words are reduced to letters/digits and quoted.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from urllib.parse import quote

# what a read-only connection may do; everything else (writes, ATTACH, PRAGMA changes, functions that load
# extensions...) is refused by SQLite before it runs
_ALLOWED = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION}
_BLOCKED_FUNCS = {"load_extension", "readfile", "writefile", "edit", "fts3_tokenizer", "zipfile"}


def quote_ident(name: str) -> str:
    """A table or column name as a quoted SQL identifier (works for any name, including ones with quotes)."""
    if "\x00" in name:
        raise ValueError("bad name")
    return '"' + name.replace('"', '""') + '"'


def like_escape(text: str) -> str:
    """For `... LIKE ? ESCAPE '\\'`: the words match literally (% and _ aren't wildcards)."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _authorizer(action, arg1, arg2, db_name, trigger):
    if action == sqlite3.SQLITE_FUNCTION and (arg2 or "").lower() in _BLOCKED_FUNCS:
        return sqlite3.SQLITE_DENY
    if action == getattr(sqlite3, "SQLITE_PRAGMA", -1) and (arg1 or "").lower() in ("table_info", "table_xinfo") and arg2 is None:
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_OK if action in _ALLOWED else sqlite3.SQLITE_DENY


def open_readonly(path: Path, timeout: float = 5.0) -> sqlite3.Connection:
    """Opens someone's .db file so that nothing in it can be changed and only reading queries run."""
    uri = "file:" + quote(str(Path(path).resolve()).replace("\\", "/")) + "?mode=ro&immutable=1"
    c = sqlite3.connect(uri, uri=True, timeout=timeout, check_same_thread=False)
    c.row_factory = sqlite3.Row
    try:
        c.enable_load_extension(False)
    except (AttributeError, sqlite3.Error):
        pass
    c.execute("PRAGMA query_only = 1")
    c.execute("PRAGMA trusted_schema = 0")       # views/triggers in the file can't call risky functions
    c.set_authorizer(_authorizer)
    return c
