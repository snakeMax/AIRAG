"""File readers: real files made by the Office libraries, plus the safety limits."""
import base64
import io
import json
import sqlite3
import zipfile

import pytest

from airag import filereaders as fr, openfile


def _xlsx():
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sales"
    ws.append(["Brand", "Units"])
    ws.append(["Volvo", 1200])
    ws["C2"] = "=B2*2"
    ws["A4"] = "site"
    ws["A4"].hyperlink = "https://example.com/sales"
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def test_xlsx_sheets_tables_links_formulas():
    d = fr.read("cars.xlsx", _xlsx())
    assert d.kind == "table" and d.tables == 1
    assert "## Sales" in d.text and "| Volvo | 1200 | =B2*2 |" in d.text
    assert d.links == ["https://example.com/sales"]


def test_docx_headings_tables_lists_links():
    docx = pytest.importorskip("docx")
    doc = docx.Document()
    doc.add_heading("Report", 1)
    doc.add_paragraph("Text 42.")
    t = doc.add_table(rows=2, cols=2)
    t.cell(0, 0).text, t.cell(0, 1).text, t.cell(1, 0).text, t.cell(1, 1).text = "Name", "Value", "A", "7"
    doc.add_paragraph("Item", style="List Bullet")
    b = io.BytesIO()
    doc.save(b)
    d = fr.read("r.docx", b.getvalue())
    assert "## Report" in d.text and "| A | 7 |" in d.text and "- Item" in d.text and d.tables == 1


def test_pptx_slides_and_notes():
    pptx = pytest.importorskip("pptx")
    p = pptx.Presentation()
    s = p.slides.add_slide(p.slide_layouts[1])
    s.shapes.title.text = "Results"
    s.placeholders[1].text = "Up 10%"
    s.notes_slide.notes_text_frame.text = "Say this"
    b = io.BytesIO()
    p.save(b)
    d = fr.read("deck.pptx", b.getvalue())
    assert d.text.startswith("## 1. Results") and "- Up 10%" in d.text and "*Notes:* Say this" in d.text


def test_csv_semicolons_and_json_records():
    d = fr.read("c.csv", b"city;pop\nOslo;700000\n")
    assert "| Oslo | 700000 |" in d.text
    d = fr.read("d.json", json.dumps({"rows": [{"a": 1}, {"a": 2, "b": "https://x.org/p"}]}).encode())
    assert "| a | b |" in d.text and d.links == ["https://x.org/p"]
    d = fr.read("e.json", b'{"just": "settings"}')
    assert d.text.startswith("```json")


def test_sqlite_is_only_read(tmp_path):
    db = tmp_path / "shop.db"
    c = sqlite3.connect(db)
    c.execute("create table items(id integer, name text)")
    c.execute("insert into items values(1, 'Lamp')")
    c.execute('create table "x""; DROP TABLE items; --"(v)')           # a hostile table name
    c.execute("create view boom as select load_extension('evil')")      # a view that tries to load code
    c.commit()
    c.close()
    before = db.read_bytes()
    d = fr.read_path(db, 10 ** 8)
    assert "| 1 | Lamp |" in d.text and d.kind == "database"
    assert db.read_bytes() == before                                      # nothing changed
    d2 = fr.read("shop.db", before)                                       # bytes only (picked/shared file)
    assert "| 1 | Lamp |" in d2.text


def test_unsafe_or_wrong_files_are_refused():
    with pytest.raises(fr.Unreadable, match="docx"):
        fr.read("old.doc", b"\xd0\xcf\x11\xe0")
    with pytest.raises(fr.Unreadable):
        fr.read("fake.db", b"not a database")
    with pytest.raises(fr.Unreadable):
        fr.read("broken.xlsx", b"PK not really")
    # a zip whose part unpacks to more than the limit
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("word/document.xml", b"<w:body>" + b"\x00" * (fr.MAX_ZIP_MEMBER + 10))
    with pytest.raises(fr.Unreadable, match="too big"):
        fr.read("bomb.docx", b.getvalue())


def test_entities_are_not_expanded():
    xml = ('<!DOCTYPE x [<!ENTITY a "AAAAAAAAAA"><!ENTITY b "&a;&a;&a;&a;">]>'
           '<w:body><w:p><w:r><w:t>&b;</w:t></w:r></w:p></w:body>')
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("word/document.xml", xml)
    d = fr.read("x.docx", b.getvalue())
    assert "AAAA" not in d.text


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from airag.main import app
    c = TestClient(app, base_url="http://127.0.0.1")
    c.get("/")                     # session cookie
    return c


def test_open_with_airag_takes_bytes(client):
    from airag import history
    data = base64.b64encode(_xlsx()).decode()
    r = client.post("/api/open-file", json={"name": "cars.xlsx", "data": data})
    assert r.status_code == 200, r.text
    rec = history.get(r.json()["id"])
    assert "| Volvo | 1200" in rec["article"] and rec["opened_file"] == "cars.xlsx"
    assert rec["sources"][0]["url"] == "https://example.com/sales"
    # plain JSON that isn't a saved article opens as data; text files still work the old way
    r = client.post("/api/open-file", json={"name": "d.json", "text": '[{"a": 1}]'})
    assert r.status_code == 200
    r = client.post("/api/open-file", json={"name": "x.doc", "data": base64.b64encode(b"\xd0\xcf").decode()})
    assert r.status_code == 400 and ".docx" in r.json()["detail"]


def test_openfile_kinds():
    assert openfile.kind_of("a.xlsx") == "doc" and openfile.kind_of("a.md") == "md"
    with pytest.raises(openfile.NotOpenable):
        openfile.kind_of("a.exe")
