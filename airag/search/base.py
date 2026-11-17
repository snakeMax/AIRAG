from __future__ import annotations

from dataclasses import dataclass
from typing import List


class SearchError(Exception):
    pass


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str = ""
    backend: str = ""


@dataclass
class ImageResult:
    title: str
    image: str
    thumbnail: str = ""
    page_url: str = ""
    width: int = 0
    height: int = 0
    source: str = ""


class SearchBackend:
    name = "base"
    label = "Base"
    supports_images = False
    fields: List[dict] = []

    def __init__(self, cfg: dict, common: dict):
        self.cfg = cfg
        self.common = common

    async def text(self, query: str, n: int = 10) -> List[SearchResult]:
        raise NotImplementedError

    async def images(self, query: str, n: int = 10) -> List[ImageResult]:
        return []


def to_int(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0
