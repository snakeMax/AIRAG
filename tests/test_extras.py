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


def test_site_lists():
    from airag.sitelists import SiteLists
    sl = SiteLists({"skip_domains": "example.com/forum, tiktok.com", "favourite_sites": "nature.com, https://www.nasa.gov/missions/"})
    assert sl.blocked_url("https://example.com/forum/thread/1") and sl.blocked_url("https://sub.example.com/forum")
    assert not sl.blocked_url("https://example.com/forums") and not sl.blocked_url("https://example.com/news")
    assert sl.blocked_url("https://www.tiktok.com/@x")
    assert sl.adjust("https://www.nature.com/articles/x", 6, "Journal")[0] == 8
    assert sl.adjust("https://nasa.gov/missions/apollo", 7, "")[0] == 9
    assert sl.adjust("https://nasa.gov/news", 7, "")[0] == 7


def test_old_default_block_list_drops_youtube():
    from airag import config
    config.save({"research": {"skip_domains": "youtube.com, tiktok.com, instagram.com, facebook.com, x.com, twitter.com, pinterest.com"}})
    assert "youtube" not in config.load()["research"]["skip_domains"]
    config.save({"research": {"skip_domains": "youtube.com"}})        # the user's own list stays
    assert config.load()["research"]["skip_domains"] == "youtube.com"


def test_youtube_ids_and_page_parsing():
    from airag import youtube
    assert youtube.video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=3") == "dQw4w9WgXcQ"
    assert youtube.video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert youtube.video_id("https://m.youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert youtube.video_id("https://youtube.com/channel/abc") is None
    assert youtube.video_id("https://notyoutube.com/watch?v=dQw4w9WgXcQ") is None
    html = '<script>var ytInitialPlayerResponse = {"videoDetails": {"title": "T"}, "captions": {}};var x=1</script>'
    assert youtube._player_response(html)["videoDetails"]["title"] == "T"
    assert youtube._player_response("<html>changed</html>") is None
    text = youtube._caption_text({"events": [{"segs": [{"utf8": "Hello"}, {"utf8": " world"}]}, {"tStartMs": 1}, {"segs": [{"utf8": "&amp; more"}]}]})
    assert text == "Hello world & more"
    tracks = [{"languageCode": "de", "kind": "asr"}, {"languageCode": "en"}, {"languageCode": "nb", "kind": "asr"}]
    assert youtube._pick_track(tracks, "nb-NO")["languageCode"] == "nb"
    assert youtube._pick_track(tracks, "fr")["languageCode"] == "en"


def test_wiki_addresses():
    from airag import wikis
    assert wikis.api_url("wikipedia", "nb-NO") == "https://no.wikipedia.org/w/api.php"
    assert wikis.api_url("wikipedia", "de") == "https://de.wikipedia.org/w/api.php"
    assert wikis.api_url("minecraft.wiki") == "https://minecraft.wiki/api.php"
    assert wikis.api_url("https://psychonautwiki.org/w/api.php") == "https://psychonautwiki.org/w/api.php"
