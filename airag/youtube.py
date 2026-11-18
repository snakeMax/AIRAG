"""Reading YouTube videos: title, channel, description and the captions (when the video has them).

YouTube has no free official API for captions, so this reads the same data the watch page uses
(the unofficial "timedtext" captions). It can break when YouTube changes its page; that case is
reported separately ("YouTube changed something") from ordinary problems like a private video.
"""
from __future__ import annotations

import asyncio
import html
import json
import re
from typing import Optional, Tuple
from urllib.parse import parse_qs, urlsplit

import httpx

_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
CHANGED = "YouTube changed something on its side, so AIRAG couldn't read this video. An AIRAG update will fix it."


def video_id(url: str) -> Optional[str]:
    try:
        u = urlsplit(url)
    except ValueError:
        return None
    host = (u.hostname or "").lower().removeprefix("www.").removeprefix("m.")
    vid = None
    if host == "youtu.be":
        vid = u.path.strip("/").split("/")[0]
    elif host in ("youtube.com", "music.youtube.com", "youtube-nocookie.com"):
        if u.path == "/watch":
            vid = (parse_qs(u.query).get("v") or [""])[0]
        else:
            m = re.match(r"^/(shorts|embed|live|v)/([^/?#]+)", u.path)
            vid = m.group(2) if m else None
    return vid if vid and _ID.match(vid) else None


def _player_response(page_html: str) -> Optional[dict]:
    m = re.search(r"ytInitialPlayerResponse\s*=\s*(\{.+?\})\s*;\s*(?:var\s|</script>)", page_html, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except ValueError:
        return None


def _pick_track(tracks: list, lang: str) -> Optional[dict]:
    if not tracks:
        return None
    lang = (lang or "en").split("-")[0].lower()

    def rank(t):
        code = str(t.get("languageCode", "")).lower()
        auto = t.get("kind") == "asr"
        return (0 if code.startswith(lang) else 1 if code.startswith("en") else 2, 1 if auto else 0)
    return sorted(tracks, key=rank)[0]


def _caption_text(data: dict) -> str:
    lines = []
    for ev in data.get("events") or []:
        segs = ev.get("segs")
        if not segs:
            continue
        line = "".join(s.get("utf8", "") for s in segs).replace("\n", " ").strip()
        if line:
            lines.append(line)
    text = " ".join(lines)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


async def _read_once(vid: str, cfg: dict) -> Tuple[dict, str]:
    headers = {"User-Agent": cfg.get("user_agent") or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/130.0 Safari/537.36",
               "Accept-Language": cfg.get("accept_language") or "en-US,en;q=0.9"}
    t = float(cfg.get("timeout") or 15)
    async with httpx.AsyncClient(follow_redirects=True, timeout=httpx.Timeout(t, connect=10), headers=headers,
                                 cookies={"CONSENT": "YES+1"}) as c:
        r = await c.get(f"https://www.youtube.com/watch?v={vid}&hl=en")
        r.raise_for_status()
        player = _player_response(r.text)
        if player is None:
            raise LookupError(CHANGED)
        status = (player.get("playabilityStatus") or {}).get("status", "OK")
        details = player.get("videoDetails") or {}
        if status not in ("OK", "LIVE_STREAM_OFFLINE") and not details:
            reason = (player.get("playabilityStatus") or {}).get("reason") or status
            raise ValueError(f"YouTube says: {reason}")
        tracks = (((player.get("captions") or {}).get("playerCaptionsTracklistRenderer") or {})
                  .get("captionTracks") or [])
        track = _pick_track(tracks, (cfg.get("accept_language") or "en").split(",")[0])
        transcript = ""
        if track and track.get("baseUrl"):
            cr = await c.get(track["baseUrl"] + "&fmt=json3")
            if cr.status_code == 200 and cr.text.strip():
                try:
                    transcript = _caption_text(cr.json())
                except ValueError:
                    transcript = ""
        return details, transcript


async def read(url: str, cfg: dict, retries: int = 1):
    """Returns a fetch.Page for a YouTube video (title + description + transcript)."""
    from .fetch import Page
    vid = video_id(url)
    if not vid:
        return Page(url, error="Not a YouTube video address")
    last: Exception = Exception("unknown error")
    for attempt in range(max(0, int(retries)) + 1):
        try:
            details, transcript = await _read_once(vid, cfg)
            break
        except LookupError as e:          # page format changed: retrying won't help
            return Page(url, error=str(e))
        except ValueError as e:           # private / removed / age-restricted
            return Page(url, error=str(e))
        except Exception as e:            # network hiccup: try again
            last = e
            if attempt < retries:
                await asyncio.sleep(1.5)
    else:
        return Page(url, error=f"YouTube couldn't be reached: {last}")
    title = details.get("title") or "YouTube video"
    desc = details.get("shortDescription") or ""
    mins = int(details.get("lengthSeconds") or 0) // 60
    parts = [f"# {title}", f"Channel: {details.get('author', '')} · {mins} min video"]
    if desc:
        parts += ["", "## Description", desc]
    if transcript:
        parts += ["", "## Transcript (from the video's captions)", transcript]
    else:
        parts += ["", "(This video has no readable captions, so only its description could be read.)"]
    thumb = f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
    return Page(url, final_url=f"https://www.youtube.com/watch?v={vid}", ok=True, title=title, text="\n".join(parts),
                description=desc[:300], site_name="YouTube", author=details.get("author", ""), og_image=thumb,
                via="youtube" + ("" if transcript else "-nocaptions"))
