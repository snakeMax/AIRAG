"""SQL injection: library search with hostile search words (from the AI or the reader), and the read-only
opener used for .db files in My library."""
import sqlite3

import pytest

from airag.library import Library
from airag.sqlsafe import like_escape, open_readonly, quote_ident

ATTACKS = [
    "'; DROP TABLE files; --",
    '" OR 1=1 --',
    "hummingbird\") OR (\"x",
    "x' UNION SELECT path, 1, 1, 1 FROM files --",
    "NEAR(wing beat) * col:text ^ -minus",
    "chunks MATCH 'a' OR 1",
    "%_% \\ ' \"",
    "ATTACH DATABASE '/tmp/evil.db' AS e",
]


def _lib(tmp_path, fts=True):
    (tmp_path / "birds.md").write_text("# Birds\n\nHummingbird wings beat between 10 and 80 times a second.",
                                       encoding="utf-8")
    (tmp_path / "rates.md").write_text("# Rates\n\n100% of 50_000 samples were fast.", encoding="utf-8")
    lib = Library(tmp_path / "idx.db")
    lib.sync([str(tmp_path)], [".md"])
    lib.fts = fts and lib.fts
    return lib


@pytest.mark.parametrize("fts", [True, False])
def test_search_survives_injection_attempts(tmp_path, fts):
    lib = _lib(tmp_path, fts)
    for attack in ATTACKS:
        lib.search([attack])                                   # never raises, never changes anything
        lib.search(["hummingbird " + attack])
    hits = lib.search(["hummingbird wings"])
    assert hits and hits[0]["title"] == "Birds"                # tables still there and intact
    c = sqlite3.connect(tmp_path / "idx.db")
    assert c.execute("SELECT COUNT(*) FROM files").fetchone()[0] == 2
    names = {r[0] for r in c.execute("SELECT name FROM sqlite_master")}
    assert {"files", "chunks"} <= names and not any("evil" in n for n in names)


def test_match_expression_contains_only_quoted_words():
    expr = Library._match_expr(ATTACKS)
    for part in expr.split(" OR "):
        assert part.startswith('"') and part.endswith('"') and '"' not in part[1:-1]
        assert part[1:-1].replace("_", "").isalnum()


def test_like_words_are_literal(tmp_path):
    lib = _lib(tmp_path, fts=False)
    assert like_escape("100%_x\\") == "100\\%\\_x\\\\"
    assert all(h["title"] != "Birds" for h in lib.search(["50_000"]))   # "_" isn't a wildcard


def test_quote_ident():
    assert quote_ident('my "table"') == '"my ""table"""'
    with pytest.raises(ValueError):
        quote_ident("a\x00b")


def test_readonly_opener_blocks_changes(tmp_path):
    db = tmp_path / "user.db"
    c = sqlite3.connect(db)
    c.execute('CREATE TABLE "birds; DROP TABLE x" (name TEXT, "rate""s" INT)')
    c.execute('INSERT INTO "birds; DROP TABLE x" VALUES (?, ?)', ("ruby-throated", 53))
    c.commit()
    c.close()
    ro = open_readonly(db)
    t = ro.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchone()["name"]
    rows = ro.execute(f"SELECT * FROM {quote_ident(t)} LIMIT 5").fetchall()
    assert rows[0]["name"] == "ruby-throated"
    for bad in [f"DELETE FROM {quote_ident(t)}", f"DROP TABLE {quote_ident(t)}", "CREATE TABLE z(a)",
                f"ATTACH DATABASE '{tmp_path / 'x.db'}' AS x", "PRAGMA query_only = 0",
                "SELECT load_extension('evil')", f"UPDATE {quote_ident(t)} SET name='x'"]:
        with pytest.raises(sqlite3.Error):
            ro.execute(bad)
    ro.close()
    c = sqlite3.connect(db)
    assert c.execute(f"SELECT COUNT(*) FROM {quote_ident(t)}").fetchone()[0] == 1
    assert not (tmp_path / "x.db").exists()
