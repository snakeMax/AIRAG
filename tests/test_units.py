import json
from pathlib import Path

from airag import config, languages
from airag.library import Library, chunks_of
from airag.passages import select_passages, tokenize

ROOT = Path(__file__).resolve().parent.parent


def test_tokenize_unicode():
    assert "hummingbird" in tokenize("Hummingbirds!")
    assert tokenize("blåbærsyltetøy") == ["blåbærsyltetøy"]
    assert tokenize("蜂鸟翅膀")  # CJK becomes bigrams


def test_select_passages_finds_buried_fact():
    filler = "Nothing to see here. " * 400
    text = filler + "\n\nThe LD50 in rats was 55 mg/kg.\n\n" + filler
    out = select_passages(text, tokenize("ld50 rats"), 1500)
    assert "55 mg/kg" in out


def test_secrets_masked_and_kept():
    config.save({"llm": {"providers": {"anthropic": {"api_key": "test-key-0123456789abcdef"}}}})
    masked = config.masked(config.load())
    assert masked["llm"]["providers"]["anthropic"]["api_key"].startswith(config.MASK)
    config.save(masked)  # saving the masked form must not overwrite the real key
    assert config.load()["llm"]["providers"]["anthropic"]["api_key"] == "test-key-0123456789abcdef"
    config.save({"llm": {"providers": {"anthropic": {"api_key": ""}}}})


def test_library_index_and_search(tmp_path):
    (tmp_path / "a.md").write_text("# Notes\n\nOsmium is the densest element.\n", encoding="utf-8")
    (tmp_path / "b.txt").write_text("Shopping: milk, eggs\n", encoding="utf-8")
    lib = Library(tmp_path / "idx.db")
    st = lib.sync([str(tmp_path)], [".md", ".txt"])
    assert st["files"] == 2
    hits = lib.search(["densest element"])
    assert hits and hits[0]["title"] == "Notes"
    (tmp_path / "b.txt").unlink()
    assert lib.sync([str(tmp_path)], [".md", ".txt"])["removed"] == 1


def test_chunks():
    assert chunks_of("---\ntitle: x\n---\nHello\n\nWorld") == ["Hello\n\nWorld"]


def test_translations_complete():
    en = json.loads((ROOT / "web" / "i18n" / "en.json").read_text(encoding="utf-8"))
    for code in [c for c, *_ in languages.LANGUAGES if languages.BY_CODE[c][3]]:
        data = json.loads((ROOT / "web" / "i18n" / f"{code}.json").read_text(encoding="utf-8"))
        assert set(data) == set(en), f"{code}.json keys differ from en.json"


def test_interactive_html_is_locked_down():
    from airag.interactive import clean_html
    html = clean_html("```html\n<html><head><title>x</title></head><body>hi</body></html>\n```")
    assert "Content-Security-Policy" in html and html.startswith("<html")


def test_damaged_settings_fall_back_to_last_good_copy():
    from airag import config
    config.save({"app": {"history_limit": 777}})
    config.save({"app": {"history_limit": 778}})          # the copy with 777 becomes the backup
    config.SETTINGS_PATH.write_text('{"app": {"history_lim', encoding="utf-8")    # half-written file
    assert config.load()["app"]["history_limit"] == 777
    assert list(config.SETTINGS_PATH.parent.glob("settings.damaged-*.json"))   # the damaged file is kept aside
    config.save({"app": {"history_limit": 300}})


def test_history_updates_dont_overwrite_each_other():
    import threading
    from airag import history
    history.save({"id": "race1", "query": "q", "outcome": "article", "article": "A", "thread": []})
    def add(i):
        history.update("race1", lambda r: r.__setitem__("thread", r["thread"] + [i]))
    ts = [threading.Thread(target=add, args=(i,)) for i in range(20)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert sorted(history.get("race1")["thread"]) == list(range(20))
    history.set_pin("race1", True)
    history.update("race1", {"article": "B"})
    history.set_pin("race1", False)
    assert not history.get("race1").get("pinned")       # the pinned flag isn't written into the record
