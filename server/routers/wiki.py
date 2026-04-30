import json
import logging
import os
import shutil

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from server.services.wiki_parser import parse_wiki_index, parse_wiki_page, search_wiki

logger = logging.getLogger(__name__)
router = APIRouter()
WIKI_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "wiki")
RAW_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "raw")


@router.get("/index")
def get_index():
    return parse_wiki_index(WIKI_DIR)


@router.get("/search")
def get_search(q: str):
    logger.info("wiki search: %s", q)
    return search_wiki(WIKI_DIR, q)


@router.get("/raw-report/{path:path}")
def get_raw_report(path: str):
    """兼容旧路由，重定向到通用 raw 文件路由。"""
    file_path = os.path.normpath(os.path.join(RAW_DIR, path))
    if not file_path.startswith(RAW_DIR + os.sep):
        raise HTTPException(status_code=403, detail="Access denied")
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="Report not found")
    return parse_wiki_page(file_path)


def _build_raw_tree() -> dict:
    industries = []
    sources = []

    if not os.path.isdir(RAW_DIR):
        return {"industries": industries, "sources": sources}

    for entry in sorted(os.listdir(RAW_DIR)):
        entry_path = os.path.join(RAW_DIR, entry)
        if not os.path.isdir(entry_path):
            continue

        if entry == "sources":
            for root, _, files in os.walk(entry_path):
                for fname in sorted(files):
                    rel = os.path.relpath(os.path.join(root, fname), RAW_DIR)
                    sources.append({"name": fname, "path": rel})
            continue

        industry = {"name": entry, "companies": [], "reports": []}

        for sub in sorted(os.listdir(entry_path)):
            sub_path = os.path.join(entry_path, sub)
            if not os.path.isdir(sub_path):
                continue

            if _is_report_dir(sub_path):
                industry["reports"].append(_parse_report_dir(sub_path, f"{entry}/{sub}"))
            else:
                company = {"name": sub, "reports": []}
                for report_dir_name in sorted(os.listdir(sub_path)):
                    report_dir_path = os.path.join(sub_path, report_dir_name)
                    if os.path.isdir(report_dir_path):
                        company["reports"].append(
                            _parse_report_dir(report_dir_path, f"{entry}/{sub}/{report_dir_name}")
                        )
                if company["reports"]:
                    industry["companies"].append(company)

        if industry["companies"] or industry["reports"]:
            industries.append(industry)

    return {"industries": industries, "sources": sources}


def _is_report_dir(path: str) -> bool:
    return os.path.isfile(os.path.join(path, "meta.json"))


def _parse_report_dir(path: str, rel_dir: str) -> dict:
    name = os.path.basename(path).replace("_", " ", 1) if "_" in os.path.basename(path) else os.path.basename(path)
    files = sorted(f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f)))
    return {"name": name, "dir": rel_dir, "files": files}


@router.get("/raw-tree")
def get_raw_tree():
    return _build_raw_tree()


@router.get("/raw/{path:path}")
def get_raw_file(path: str):
    file_path = os.path.normpath(os.path.join(RAW_DIR, path))
    if not file_path.startswith(RAW_DIR + os.sep):
        raise HTTPException(status_code=403, detail="Access denied")
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    if file_path.endswith(".pdf"):
        return FileResponse(file_path, media_type="application/pdf")
    if file_path.endswith(".md"):
        return parse_wiki_page(file_path)
    if file_path.endswith(".json"):
        with open(file_path, "r", encoding="utf-8") as f:
            return JSONResponse(json.load(f))
    raise HTTPException(status_code=404, detail="Unsupported file type")


def _safe_wiki_path(rel: str) -> str:
    full = os.path.normpath(os.path.join(WIKI_DIR, rel))
    if not full.startswith(WIKI_DIR + os.sep) and full != WIKI_DIR:
        raise HTTPException(status_code=403, detail="Access denied")
    return full


def _build_wiki_tree() -> list[dict]:
    result = []
    for entry in sorted(os.listdir(WIKI_DIR)):
        entry_path = os.path.join(WIKI_DIR, entry)
        if entry.startswith("."):
            continue
        if os.path.isdir(entry_path):
            result.append(_tree_node(entry_path, entry))
        elif entry.endswith(".md"):
            result.append({"name": entry, "path": entry, "type": "file"})
    return result


def _tree_node(abs_path: str, rel_path: str) -> dict:
    children = []
    for entry in sorted(os.listdir(abs_path)):
        child_abs = os.path.join(abs_path, entry)
        child_rel = f"{rel_path}/{entry}"
        if entry.startswith("."):
            continue
        if os.path.isdir(child_abs):
            children.append(_tree_node(child_abs, child_rel))
        elif entry.endswith(".md"):
            children.append({"name": entry, "path": child_rel, "type": "file"})
    return {"name": os.path.basename(abs_path), "path": rel_path, "type": "dir", "children": children}


@router.get("/tree")
def get_wiki_tree():
    return _build_wiki_tree()


class MkdirRequest(BaseModel):
    path: str


@router.post("/mkdir")
def wiki_mkdir(req: MkdirRequest):
    target = _safe_wiki_path(req.path)
    if os.path.exists(target):
        raise HTTPException(status_code=409, detail="Already exists")
    os.makedirs(target)
    return {"ok": True}


class MoveRequest(BaseModel):
    src: str
    dst: str


@router.post("/move")
def wiki_move(req: MoveRequest):
    src = _safe_wiki_path(req.src)
    dst = _safe_wiki_path(req.dst)
    if not os.path.isfile(src):
        raise HTTPException(status_code=404, detail="Source not found")
    if os.path.exists(dst):
        raise HTTPException(status_code=409, detail="Destination already exists")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.move(src, dst)
    return {"ok": True}


@router.get("/{path:path}")
def get_page(path: str):
    file_path = os.path.normpath(os.path.join(WIKI_DIR, path))
    if not file_path.startswith(WIKI_DIR + os.sep):
        raise HTTPException(status_code=403, detail="Access denied")
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="Page not found")
    return parse_wiki_page(file_path)
