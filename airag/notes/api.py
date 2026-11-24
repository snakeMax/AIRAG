"""HTTP routes for Notes (mounted under /api/notes by airag.main). No AI here."""
from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import config
from . import index, pathguard, search, store

router = APIRouter(prefix="/api/notes")


def _vault(vid: str):
    s = config.load()
    try:
        v = store.get_vault(s, vid)
    except store.NotesError as e:
        raise HTTPException(404, str(e))
    if not store.vault_dir(s, v).is_dir():
        raise HTTPException(404, "The vault's folder is missing (moved or on a drive that isn't connected)")
    return s, v


def _fail(e: Exception, code: int = 400):
    return HTTPException(code, str(e))


@router.get("/vaults")
def list_vaults():
    s = config.load()
    return {"root": str(store.root(s)), "vaults": store.vaults(s), "templates": list(store.TEMPLATES),
            "types": store.NOTE_TYPES}


class NewVault(BaseModel):
    name: str
    template: str = "research"
    purpose: str = ""


@router.post("/vaults")
def new_vault(req: NewVault):
    try:
        return store.create_vault(config.load(), req.name, req.template, req.purpose)
    except (store.NotesError, pathguard.PathError, OSError) as e:
        raise _fail(e)


class LinkVault(BaseModel):
    folder: str
    name: str = ""


@router.post("/vaults/link")
def link_vault(req: LinkVault):
    try:
        return store.link_vault(config.load(), req.folder, req.name)
    except (store.NotesError, OSError) as e:
        raise _fail(e)


@router.delete("/vaults/{vid}")
def forget_vault(vid: str):
    store.forget_vault(config.load(), vid)       # the files stay where they are
    return {"ok": True}


@router.get("/{vid}/tree")
def tree(vid: str):
    s, v = _vault(vid)
    return {"items": store.tree(s, v)}


@router.post("/{vid}/reindex")
async def reindex(vid: str):
    s, v = _vault(vid)
    try:
        return await asyncio.to_thread(index.update, s, v)
    except store.NotesError as e:
        raise _fail(e)


@router.get("/{vid}/note")
def get_note(vid: str, path: str):
    s, v = _vault(vid)
    try:
        text = store.read_note(s, v, path)
    except FileNotFoundError:
        raise HTTPException(404, "That note doesn't exist")
    except (store.NotesError, pathguard.PathError) as e:
        raise _fail(e)
    from .parser import parse, split_front_matter
    n = parse(text, path.rsplit("/", 1)[-1][:-3] if path.lower().endswith(".md") else path)
    return {"path": path, "text": text, "hash": n.hash, "title": n.title, "props": split_front_matter(text)[0],
            "tags": n.tags, "outline": [{"heading": x.heading, "level": x.level, "ord": x.ord} for x in n.sections if x.heading],
            "linked_vault": bool(v.get("linked"))}


class SaveNote(BaseModel):
    path: str
    text: str
    hash: Optional[str] = None
    approved: bool = False


@router.put("/{vid}/note")
async def save_note(vid: str, req: SaveNote):
    s, v = _vault(vid)
    try:
        r = store.write_note(s, v, req.path, req.text, expected_hash=req.hash, approved=req.approved)
    except store.NotesError as e:
        raise _fail(e, 409)
    except (pathguard.PathError, OSError) as e:
        raise _fail(e)
    await asyncio.to_thread(index.reindex_one, s, v, r["path"])
    return r


class NewNote(BaseModel):
    folder: str = ""
    title: str
    body: str = ""
    props: dict = {}


@router.post("/{vid}/new")
async def new_note(vid: str, req: NewNote):
    s, v = _vault(vid)
    try:
        r = store.create_note(s, v, req.folder, req.title, req.body, req.props)
    except (store.NotesError, pathguard.PathError, OSError) as e:
        raise _fail(e)
    await asyncio.to_thread(index.reindex_one, s, v, r["path"])
    return r


@router.get("/{vid}/search")
async def search_notes(vid: str, q: str = "", sort: str = "relevance"):
    s, v = _vault(vid)
    try:
        return await asyncio.to_thread(search.run, s, v, q, sort)
    except search.QueryError as e:
        raise _fail(e)


@router.get("/{vid}/links")
def links(vid: str, path: str):
    s, v = _vault(vid)
    try:
        pathguard.clean_rel(path)
    except pathguard.PathError as e:
        raise _fail(e)
    return {"backlinks": index.backlinks(s, v, path), "outgoing": index.outgoing(s, v, path)}


@router.get("/{vid}/stats")
def vault_stats(vid: str):
    s, v = _vault(vid)
    return index.stats(s, v)
