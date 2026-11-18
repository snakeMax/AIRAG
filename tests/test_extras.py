"""Sound clips, pinned searches and the standalone web page export."""
import base64

import pytest

from airag import export_html, history, sounds


def test_sound_upload_checks_the_file():
    wav = (sounds.paths.WEB_DIR / "sounds" / "mic-start.wav").read_bytes()
    name = sounds.save("mic_start", base64.b64encode(wav).decode(), "wav")
    assert name == "mic_start.wav" and sounds.custom_file("mic_start")
    with pytest.raises(ValueError):          # a WAV renamed to .mp3 is refused
        sounds.save("mic_start", base64.b64encode(wav).decode(), "mp3")
    with pytest.raises(ValueError):
        sounds.save("mic_start", base64.b64encode(b"<script>").decode(), "exe")
    with pytest.raises(ValueError):
        sounds.save("../../evil", base64.b64encode(wav).decode(), "wav")
    sounds.remove("mic_start")
    assert sounds.custom_file("mic_start") is None
    assert all(sounds.default_file(n) for n in sounds.NAMES)


def test_pins_survive_pruning():
    history.clear()
    for i in range(5):
        history.save({"id": f"p{i}", "query": f"q{i}", "outcome": "article"}, limit=100)
    history.set_pin("p0", True)
    history.prune(2)
    ids = {r["id"] for r in history.listing()}
    assert "p0" in ids and len(ids) == 3          # 2 newest + the pinned one
    assert history.get("p0")["pinned"] is True
    history.set_pin("p0", False)
    assert not history.get("p0").get("pinned")


def test_export_is_cleaned_and_standalone():
    rec = {"id": "x", "outcome": "article", "interactive_html": "<script>alert(1)</script><p>game</p>"}
    body = ('<article><h1 onclick="steal()">Title</h1><script>bad()</script><p>Text <a href="javascript:x()">x</a>'
            '<a href="https://example.org">ok</a></p><button>Save</button><iframe src="https://evil"></iframe></article>')
    out = export_html.build(rec, body, "Title")
    assert "steal()" not in out and "bad()" not in out and "javascript:" not in out and "https://evil" not in out
    assert 'href="https://example.org"' in out and "<button" not in out
    assert 'sandbox="allow-scripts"' in out and "&lt;script&gt;alert(1)" in out   # explainer only inside the sandbox
    assert "Content-Security-Policy" in out


def test_pinned_sources():
    from airag import pinned
    item = pinned.add("https://example.org/bees", "How bees dance", "Honey bees dance to show where flowers are. " * 20,
                      {"domain": "example.org", "query": "bee dance"})
    assert pinned.is_pinned("https://example.org/bees")
    assert pinned.matching(["bees", "dance", "flowers"])[0]["text"].startswith("Honey bees")   # original text, not lower-cased
    assert pinned.matching(["volcano", "lava"]) == []
    assert pinned.get(item["id"])["text"]
    with pytest.raises(ValueError):
        pinned.add("file:///etc/passwd", "x", "x")
    assert pinned.remove(item["id"]) and not pinned.is_pinned("https://example.org/bees")
