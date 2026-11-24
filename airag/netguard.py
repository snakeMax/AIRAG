"""Keeps AIRAG's own page reader away from your computer and your local network.

Pages are read for searches, "links in your question", shared links and (later) web tabs' Download page /
Add source. A link could point at this computer (127.0.0.1), the home router, a NAS or other devices on the
local network; reading those and sending the text to the AI would leak private data, so only public
http(s) addresses are read. Settings -> Searching -> "Read pages on my local network" (off) allows them.

Every redirect is checked too. Names are resolved and every address they resolve to must be public.
"""
from __future__ import annotations

import asyncio
import ipaddress
import socket
from typing import Optional
from urllib.parse import urlsplit

MESSAGE = "Not read: this link points to your computer or local network"
LOCAL_SUFFIXES = (".local", ".localhost", ".lan", ".home", ".internal", ".intranet", ".corp", ".home.arpa")


def _bad_ip(ip: ipaddress._BaseAddress) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return not ip.is_global or ip.is_multicast


def _literal_problem(url: str) -> tuple[Optional[str], Optional[str]]:
    """(problem, host to resolve)."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return "Not read: the link isn't a valid web address", None
    if parts.scheme not in ("http", "https"):
        return "Not read: only http and https links are read", None
    host = (parts.hostname or "").strip(".").lower()
    if not host:
        return "Not read: the link has no address", None
    if parts.username or parts.password:
        return "Not read: links with a user name or password aren't read", None
    if host == "localhost" or host.endswith(LOCAL_SUFFIXES) or "." not in host and ":" not in host:
        return MESSAGE, None          # single-label names (e.g. "router", "nas") are local
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        try:      # odd IPv4 spellings browsers accept: 2130706433, 0x7f.1, 127.1
            ip = ipaddress.ip_address(socket.inet_aton(host)) if all(c in "0123456789abcdefx." for c in host) else None
        except OSError:
            ip = None
    if ip is not None:
        return (MESSAGE if _bad_ip(ip) else None), None
    return None, host


def allowed_local(settings_fetch: Optional[dict]) -> bool:
    return bool((settings_fetch or {}).get("allow_local_network"))


def check_sync(url: str, allow_local: bool = False) -> Optional[str]:
    """A reason the URL must not be read, or None. Resolves the name (blocking)."""
    problem, host = _literal_problem(url)
    if problem and (problem != MESSAGE or not allow_local):
        return problem
    if host is None or allow_local:
        return None
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError, OSError):
        return None                     # can't resolve: the fetch itself will fail with its own error
    for info in infos:
        try:
            if _bad_ip(ipaddress.ip_address(info[4][0].split("%")[0])):
                return MESSAGE
        except ValueError:
            continue
    return None


async def check(url: str, allow_local: bool = False) -> Optional[str]:
    return await asyncio.to_thread(check_sync, url, allow_local)
