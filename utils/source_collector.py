"""
外部资源收集器：下载研究员引用的 URL，保存到 raw/sources/。
PDF 保留原件 + 提取文本为 .md，HTML 提取正文为 .md，失败静默跳过。
"""
import asyncio
import logging
import os
import re
import tempfile
from datetime import date
from typing import Callable, Optional

import httpx

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
_SOURCES_DIR = os.path.join(_PROJECT_ROOT, "raw", "sources")

_UNSAFE_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _make_slug(title: str) -> str:
    slug = _UNSAFE_CHARS.sub("", title).replace(" ", "_").strip("._")
    return slug[:60] or "untitled"


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    import fitz
    pages = []
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        for page in doc:
            text = page.get_text()
            if text.strip():
                pages.append(text)
    return "\n\n---\n\n".join(pages)


def _extract_html_text(html: str) -> str:
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<[^>]+>', '\n', html)
    html = re.sub(r'\n{3,}', '\n\n', html)
    text = html.strip()
    if len(text) < 50:
        return ""
    return text


async def _download_one(
    client: httpx.AsyncClient,
    url: str,
    title: str,
    dest_dir: str,
    today: str,
    relpath_base: str | None = None,
) -> Optional[dict]:
    """下载单个 URL，返回 {"title", "url", "path"} 或 None。"""
    base = relpath_base or _PROJECT_ROOT
    slug = _make_slug(title)
    try:
        resp = await client.get(url, follow_redirects=True, timeout=30.0)
        resp.raise_for_status()
    except Exception as e:
        logger.debug("下载失败 %s: %s", url, e)
        return None

    content_type = resp.headers.get("content-type", "").lower()

    if "application/pdf" in content_type:
        pdf_path = os.path.join(dest_dir, f"{today}_{slug}.pdf")
        md_path = os.path.join(dest_dir, f"{today}_{slug}.md")
        if os.path.exists(md_path):
            return {"title": title, "url": url, "path": os.path.relpath(md_path, base)}
        if os.path.exists(pdf_path):
            return {"title": title, "url": url, "path": os.path.relpath(pdf_path, base)}
        os.makedirs(dest_dir, exist_ok=True)
        with open(pdf_path, "wb") as f:
            f.write(resp.content)
        try:
            text = _extract_pdf_text(resp.content)
            if text.strip():
                md_content = f"---\nsource: {url}\ntitle: {title}\ndate: {today}\ntype: pdf\n---\n\n{text}\n"
                with open(md_path, "w", encoding="utf-8") as f:
                    f.write(md_content)
                return {"title": title, "url": url, "path": os.path.relpath(md_path, base)}
        except Exception as e:
            logger.warning("PDF 文本提取失败 %s: %s", url, e)
        return {"title": title, "url": url, "path": os.path.relpath(pdf_path, base)}

    if "text/html" in content_type:
        md_path = os.path.join(dest_dir, f"{today}_{slug}.md")
        if os.path.exists(md_path):
            return {"title": title, "url": url, "path": os.path.relpath(md_path, base)}
        text = _extract_html_text(resp.text)
        if not text:
            return None
        os.makedirs(dest_dir, exist_ok=True)
        md_content = f"---\nsource: {url}\ntitle: {title}\ndate: {today}\ntype: html\n---\n\n{text}\n"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_content)
        return {"title": title, "url": url, "path": os.path.relpath(md_path, base)}

    return None


async def download_single_url(url: str, dest_dir: str, title: str = "") -> Optional[dict]:
    """下载单个 URL 到指定目录，返回 {"title", "url", "path"} 或 None。"""
    today = date.today().isoformat()
    async with httpx.AsyncClient(
        headers={"User-Agent": "Mozilla/5.0 (compatible; LucasBot/1.0)"},
    ) as client:
        return await _download_one(client, url, title, dest_dir, today)


async def collect_sources(
    source_urls: list[dict],
    industry: str,
    companies: list[str],
    sources_dir: str | None = None,
    relpath_base: str | None = None,
    on_status: Optional[Callable] = None,
) -> list[dict]:
    """
    下载 source_urls 中的资源到 sources_dir/{行业}/{公司}/。
    返回成功保存的文件列表 [{"title", "url", "path"}]。
    """
    if not source_urls:
        return []

    base_dir = sources_dir or _SOURCES_DIR
    industry = industry or "未分类"
    if companies:
        dest_dir = os.path.join(base_dir, industry, companies[0])
    else:
        dest_dir = os.path.join(base_dir, industry)

    today = date.today().isoformat()
    sem = asyncio.Semaphore(3)
    collected = []

    def status(msg: str):
        if on_status:
            on_status(msg)

    status(f"正在收集 {len(source_urls)} 个外部资源...")

    async with httpx.AsyncClient(
        headers={"User-Agent": "Mozilla/5.0 (compatible; LucasBot/1.0)"},
    ) as client:
        async def _task(item: dict):
            async with sem:
                result = await _download_one(
                    client, item["url"], item.get("title", ""), dest_dir, today,
                    relpath_base=relpath_base,
                )
                if result:
                    collected.append(result)

        await asyncio.gather(*[_task(item) for item in source_urls], return_exceptions=True)

    if collected:
        status(f"收集完成，保存了 {len(collected)}/{len(source_urls)} 个资源")
    else:
        status("未能收集到外部资源（全部跳过或失败）")

    return collected
