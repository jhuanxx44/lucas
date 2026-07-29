"""Wiki 规模实验的数据协议、质量校验与可见子库物化。"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path, PurePosixPath
from typing import Iterable
from urllib.parse import urlparse

import yaml


_DOC_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_SOURCE_MARKER_RE = re.compile(r"\[(S\d+)\]")
# 正文中任何数字都视为需要来源的高风险事实；来源章节和 frontmatter 单独排除。
_NUMERIC_RE = re.compile(r"\d")
_PAGE_TYPES = {"company", "industry", "concept"}


def load_jsonl(path: Path) -> list[dict]:
    entries = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_number}: entry must be an object")
        entries.append(value)
    return entries


def validate_source_plan(entries: list[dict]) -> list[str]:
    errors = []
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    seen_urls: set[str] = set()
    for index, entry in enumerate(entries, 1):
        prefix = f"entry {index}"
        doc_id = entry.get("doc_id")
        if not isinstance(doc_id, str) or not _DOC_ID_RE.fullmatch(doc_id):
            errors.append(f"{prefix}: invalid doc_id")
        elif doc_id in seen_ids:
            errors.append(f"{prefix}: duplicate doc_id: {doc_id}")
        else:
            seen_ids.add(doc_id)

        target_path = entry.get("target_path")
        if not _safe_relative_markdown_path(target_path):
            errors.append(f"{prefix}: unsafe target_path")
        elif target_path in seen_paths:
            errors.append(f"{prefix}: duplicate target_path: {target_path}")
        else:
            seen_paths.add(target_path)

        if entry.get("page_type") not in _PAGE_TYPES:
            errors.append(f"{prefix}: page_type must be one of {sorted(_PAGE_TYPES)}")
        if entry.get("source_tier") not in (1, 2, 3):
            errors.append(f"{prefix}: source_tier must be 1, 2, or 3")
        if not isinstance(entry.get("domain"), str) or not entry["domain"].strip():
            errors.append(f"{prefix}: domain is required")
        if not isinstance(entry.get("reason"), str) or not entry["reason"].strip():
            errors.append(f"{prefix}: reason is required")

        urls = entry.get("urls")
        if not isinstance(urls, list) or not urls:
            errors.append(f"{prefix}: urls must be a non-empty list")
        else:
            for url in urls:
                parsed = urlparse(url) if isinstance(url, str) else None
                if parsed is None or parsed.scheme != "https" or not parsed.netloc:
                    errors.append(f"{prefix}: URL must use https: {url}")
                elif url in seen_urls:
                    errors.append(f"{prefix}: duplicate source URL: {url}")
                else:
                    seen_urls.add(url)
        url_tiers = entry.get("url_tiers")
        if url_tiers is not None:
            if (not isinstance(url_tiers, list) or not isinstance(urls, list)
                    or len(url_tiers) != len(urls)
                    or any(tier not in (1, 2, 3) for tier in url_tiers)):
                errors.append(f"{prefix}: url_tiers must align with urls and use tiers 1-3")
    return errors


def snapshot_record(source: dict, snapshot_path: Path, retrieved_at: str) -> dict:
    data = json.loads(snapshot_path.read_text(encoding="utf-8"))
    markdown = data.get("markdown")
    metadata = data.get("metadata") or {}
    if not isinstance(markdown, str) or not markdown.strip():
        return {
            "doc_id": source["doc_id"],
            "status": "invalid_snapshot",
            "retrieved_at": retrieved_at,
        }
    return {
        **source,
        "status": "ok",
        "retrieved_at": retrieved_at,
        "snapshot_path": snapshot_path.as_posix(),
        "source_url": metadata.get("sourceURL") or source["urls"][0],
        "source_title": metadata.get("title", ""),
        "status_code": metadata.get("statusCode"),
        "scrape_id": metadata.get("scrapeId"),
        "markdown_chars": len(markdown),
        "content_sha256": hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
    }


def validate_wiki_page(page_path: Path, catalog_source_ids: set[str]) -> list[str]:
    errors = []
    text = page_path.read_text(encoding="utf-8")
    frontmatter, body = _frontmatter(text)
    if frontmatter is None:
        return [f"{page_path}: missing or invalid frontmatter"]

    for field in ("title", "type", "as_of", "summary", "source_ids"):
        if not frontmatter.get(field):
            errors.append(f"{page_path}: missing frontmatter.{field}")
    if frontmatter.get("type") not in _PAGE_TYPES:
        errors.append(f"{page_path}: invalid frontmatter.type")
    source_ids = frontmatter.get("source_ids")
    if not isinstance(source_ids, list) or not all(isinstance(value, str) for value in source_ids):
        errors.append(f"{page_path}: frontmatter.source_ids must be a string list")
        source_ids = []

    used_markers = set(_SOURCE_MARKER_RE.findall(body))
    declared = set(source_ids)
    unknown = (declared | used_markers) - catalog_source_ids
    if unknown:
        errors.append(f"{page_path}: unknown source ids: {sorted(unknown)}")
    if used_markers - declared:
        errors.append(f"{page_path}: body uses undeclared source ids")
    if declared - used_markers:
        errors.append(f"{page_path}: declared source ids are not cited in body")

    content_before_sources = body.split("\n## 来源", 1)[0]
    for line_number, line in enumerate(content_before_sources.splitlines(), 1):
        if line.lstrip().startswith("#"):
            continue
        if _NUMERIC_RE.search(line) and not _SOURCE_MARKER_RE.search(line):
            errors.append(
                f"{page_path}:{line_number}: numeric claim lacks source marker"
            )
    if "## 来源" not in body:
        errors.append(f"{page_path}: missing sources section")
    return errors


def materialize_manifest(master_wiki: Path, manifest_path: Path,
                         destination_wiki: Path) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    documents = manifest.get("documents")
    if not isinstance(documents, list) or not documents:
        raise ValueError("manifest.documents must be a non-empty list")
    if manifest.get("size") != len(documents):
        raise ValueError("manifest.size does not match documents")
    if len(set(documents)) != len(documents):
        raise ValueError("manifest.documents must be unique")

    if destination_wiki.exists():
        shutil.rmtree(destination_wiki)
    destination_wiki.mkdir(parents=True)
    copied = []
    for relative in documents:
        if not _safe_relative_markdown_path(relative):
            raise ValueError(f"unsafe manifest path: {relative}")
        source = (master_wiki / relative).resolve()
        root = master_wiki.resolve()
        if root not in source.parents or not source.is_file() or source.is_symlink():
            raise ValueError(f"manifest document missing or unsafe: {relative}")
        destination = destination_wiki / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied.append(relative)

    write_wiki_index(destination_wiki, copied)
    digest = hashlib.sha256(
        "\n".join(sorted(copied)).encode("utf-8")
    ).hexdigest()
    return {"document_count": len(copied), "documents_sha256": digest}


def write_wiki_index(wiki_root: Path, documents: Iterable[str]) -> None:
    groups: dict[str, list[str]] = {}
    for relative in sorted(documents):
        path = PurePosixPath(relative)
        section = " · ".join(path.parts[:-1]) or "根目录"
        groups.setdefault(section, []).append(relative)
    lines = ["# Wiki 索引", ""]
    for section, paths in groups.items():
        lines.extend([f"## {section}", ""])
        for relative in paths:
            name = PurePosixPath(relative).stem
            lines.append(f"- [{name}]({relative})")
        lines.append("")
    (wiki_root / "index.md").write_text("\n".join(lines), encoding="utf-8")


def _safe_relative_markdown_path(value: object) -> bool:
    if not isinstance(value, str) or not value.endswith(".md"):
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and ".." not in path.parts and value != "index.md"


def _frontmatter(text: str) -> tuple[dict | None, str]:
    if not text.startswith("---\n"):
        return None, text
    parts = text.split("---", 2)
    if len(parts) != 3:
        return None, text
    try:
        value = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return None, text
    return (value if isinstance(value, dict) else None), parts[2]
