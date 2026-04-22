import logging
import os

from fastapi import APIRouter, HTTPException
from server.services.wiki_parser import parse_wiki_index, parse_wiki_page, search_wiki

logger = logging.getLogger(__name__)
router = APIRouter()
WIKI_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "wiki")


@router.get("/index")
def get_index():
    return parse_wiki_index(WIKI_DIR)


@router.get("/search")
def get_search(q: str):
    logger.info("wiki search: %s", q)
    return search_wiki(WIKI_DIR, q)


@router.get("/{path:path}")
def get_page(path: str):
    file_path = os.path.normpath(os.path.join(WIKI_DIR, path))
    if not file_path.startswith(WIKI_DIR + os.sep):
        raise HTTPException(status_code=403, detail="Access denied")
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="Page not found")
    return parse_wiki_page(file_path)
