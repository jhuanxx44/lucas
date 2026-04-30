import json
import logging
import os
import shutil

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
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


class FetchSourceRequest(BaseModel):
    url: str


@router.post("/fetch-source")
async def fetch_source(req: FetchSourceRequest):
    """抓取 URL 内容，返回提取的文本（不存储）。"""
    if not req.url.strip():
        raise HTTPException(status_code=400, detail="url 不能为空")

    from utils.source_collector import _extract_html_text, _extract_pdf_text
    import httpx

    try:
        async with httpx.AsyncClient(
            headers={"User-Agent": "Mozilla/5.0 (compatible; LucasBot/1.0)"},
        ) as client:
            resp = await client.get(req.url, follow_redirects=True, timeout=30.0)
            resp.raise_for_status()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"抓取失败: {e}")

    content_type = resp.headers.get("content-type", "").lower()

    if "application/pdf" in content_type:
        try:
            text = _extract_pdf_text(resp.content)
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"PDF 解析失败: {e}")
    elif "text/html" in content_type:
        text = _extract_html_text(resp.text)
    else:
        raise HTTPException(status_code=422, detail=f"不支持的内容类型: {content_type}")

    if not text or len(text) < 50:
        raise HTTPException(status_code=422, detail="提取的内容过短或为空")

    return {"content": text, "url": req.url, "content_type": content_type}


class ClassifySourceRequest(BaseModel):
    content: str


_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
_PROMPTS_DIR = os.path.join(_PROJECT_ROOT, "prompts")
_MEMORY_DIR = os.path.join(_PROJECT_ROOT, "memory")


def _create_knowledge_service():
    from agents.config import load_config
    from agents.knowledge_service import KnowledgeService
    from agents.memory import ManagerMemory
    from utils.llm_client import create_client

    config = load_config()
    client = create_client(
        model=config.manager.model,
        system_prompt=config.manager.system_prompt,
        enable_thinking=False,
    )
    memory = ManagerMemory(_MEMORY_DIR)

    def _load_prompt(name: str) -> str:
        path = os.path.join(_PROMPTS_DIR, f"{name}.md")
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        if content.startswith("---\n"):
            end = content.find("\n---\n", 4)
            if end != -1:
                content = content[end + 5:]
        return content

    return KnowledgeService(client, memory, _load_prompt)


@router.post("/classify-source")
async def classify_source(req: ClassifySourceRequest):
    """对材料内容做分类，返回 {title, industry, company}。"""
    if not req.content.strip():
        raise HTTPException(status_code=400, detail="content 不能为空")

    ks = _create_knowledge_service()
    result = await ks.classify_source(req.content)
    return result


class IngestSourceRequest(BaseModel):
    content: str
    url: str = ""
    title: str
    industry: str
    company: str = ""


@router.post("/ingest-source")
async def ingest_source(req: IngestSourceRequest):
    """存储已确认的材料并编译进 wiki（SSE 流式返回进度）。"""
    if not req.content.strip():
        raise HTTPException(status_code=400, detail="content 不能为空")
    if not req.title.strip():
        raise HTTPException(status_code=400, detail="title 不能为空")
    if not req.industry.strip():
        raise HTTPException(status_code=400, detail="industry 不能为空")

    async def _stream():
        ks = _create_knowledge_service()

        events = []

        def on_status(msg):
            events.append(("status", {"message": msg}))

        try:
            result = await ks.ingest_source(
                content=req.content,
                url=req.url,
                title=req.title,
                industry=req.industry,
                company=req.company,
                on_status=on_status,
            )
            events.append(("saved", {"path": result["path"]}))
            events.append(("compiled", {"pages": result["compiled_pages"]}))
            events.append(("done", result))
        except Exception as e:
            logger.exception("ingest-source error")
            events.append(("error", {"message": str(e)}))

        for event_type, data in events:
            yield f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


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
