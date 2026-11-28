"""HTTP routes for Notes (mounted under /api/notes by airag.main). The AI routes (/organize, /ask) run as normal
background jobs through the run manager and only return a proposal or an answer (nothing is written)."""
from __future__ import annotations

import asyncio
from pathlib import Path
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


@router.get("/folder")
def notes_folder():
    return store.status(config.load())


class FolderReq(BaseModel):
    path: Optional[str] = None      # None = ask with the folder picker, "" = back to the default


@router.post("/folder")
async def set_notes_folder(req: FolderReq):
    """Where the Notes folder is. Vaults already made stay where they are; the list of vaults is kept per
    Notes folder (notes-index.json), so switching back finds them again."""
    from .. import appctl
    path = req.path
    if path is None:
        try:
            path = await asyncio.to_thread(appctl.pick_folder)
        except RuntimeError as e:
            raise _fail(e)
        if not path:
            return store.status(config.load())
    if path:
        p = Path(path.strip().strip('"')).expanduser()
        if not p.is_absolute():
            raise HTTPException(400, "Pick a full folder path")
        try:
            p.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise HTTPException(400, f"Can't use that folder: {e}")
        path = str(p)
    s = config.save({"notes": {"root": path}})
    return store.status(s)


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


@router.get("/{vid}/tags")
def vault_tags(vid: str):
    s, v = _vault(vid)
    return {"tags": index.all_tags(s, v)}


@router.get("/{vid}/stats")
def vault_stats(vid: str):
    s, v = _vault(vid)
    return index.stats(s, v)


class OrganizeReq(BaseModel):
    text: str
    ui_lang: Optional[str] = None


@router.post("/{vid}/organize")
async def organize_note(vid: str, req: OrganizeReq):
    """AI proposal for a voice note: title, folder, type, tags, links and tidied text. Saving is a separate step."""
    from ..main import _job_result          # the shared AI job helper (queued, shown in the activity bar)
    from . import organize
    s, v = _vault(vid)
    if not req.text.strip():
        raise HTTPException(400, "Say or type something first")
    return await _job_result(lambda: organize.organize(s, v, req.text, req.ui_lang), "notes-organize",
                             req.text.strip()[:80])


class AskReq(BaseModel):
    q: str
    ui_lang: Optional[str] = None


@router.post("/{vid}/ask")
async def ask_notes(vid: str, req: AskReq):
    """Smart search / Ask your notes: a short cited answer from the vault, plus results in tiers."""
    from ..main import _job_result
    from . import smart
    s, v = _vault(vid)
    if not req.q.strip():
        raise HTTPException(400, "Type or say a question first")
    return await _job_result(lambda: smart.ask(s, v, req.q, req.ui_lang), "notes-ask", req.q.strip()[:80])


class CategorizeReq(BaseModel):
    text: str
    title: str = ""
    ui_lang: Optional[str] = None


@router.post("/{vid}/categorize")
async def categorize_research(vid: str, req: CategorizeReq):
    """Research -> notes, Auto-categorize: proposes title, folder, type, tags and related notes; the text is kept."""
    from ..main import _job_result
    from . import organize
    s, v = _vault(vid)
    if not req.text.strip():
        raise HTTPException(400, "Nothing to add")
    return await _job_result(lambda: organize.categorize(s, v, req.text[:200_000], req.title[:300], req.ui_lang),
                             "notes-organize", (req.title or req.text).strip()[:80])
