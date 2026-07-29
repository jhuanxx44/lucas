"""wiki 解析与召回核心：server（Wiki API）与 harness（wiki_recall 工具）共用。

自 server/services/wiki_parser.py 上移（M3），原模块保留为 re-export 兼容层。
"""
import math
import os
import re

import yaml

from utils.path_safety import resolve_within

_LINK_RE = re.compile(r'-\s+\[([^\]]+)\]\(([^)]+)\)(?:\s*—\s*(.+))?')
_WIKI_LINK_RE = re.compile(r'\[\[([^\]]+)\]\]')


def parse_wiki_index(wiki_dir: str) -> dict:
    sections = []

    def _scan_grouped(subdir: str, label: str, name_transform=None):
        base = os.path.join(wiki_dir, subdir)
        if not os.path.isdir(base):
            return
        for entry in sorted(os.listdir(base)):
            entry_path = os.path.join(base, entry)
            if os.path.isdir(entry_path):
                items = []
                for root, _, files in os.walk(entry_path):
                    for fname in sorted(files):
                        if not fname.endswith(".md"):
                            continue
                        rel = os.path.relpath(os.path.join(root, fname), os.path.join(wiki_dir))
                        name = name_transform(fname) if name_transform else fname.replace(".md", "")
                        items.append({"name": name, "path": rel})
                if items:
                    sections.append({"title": f"{label} · {entry}", "items": items})

    def _scan_flat(subdir: str, label: str):
        base = os.path.join(wiki_dir, subdir)
        if not os.path.isdir(base):
            return
        items = []
        for fname in sorted(os.listdir(base)):
            if not fname.endswith(".md"):
                continue
            items.append({"name": fname.replace(".md", ""), "path": f"{subdir}/{fname}"})
        if items:
            sections.append({"title": label, "items": items})

    def _report_name(fname):
        name = fname.replace(".md", "")
        return name.split("_", 1)[1] if "_" in name else name

    def _scan_root(label: str):
        # 兜底：扫描 wiki 根目录下未归类的散落 .md 文件（排除 index/glossary），
        # 保证任何写入 wiki 的文件都能在侧栏可见，不会"消失"。
        items = []
        for fname in sorted(os.listdir(wiki_dir)):
            if not fname.endswith(".md") or fname in ("index.md", "glossary.md"):
                continue
            if not os.path.isfile(os.path.join(wiki_dir, fname)):
                continue
            items.append({"name": fname.replace(".md", ""), "path": fname})
        if items:
            sections.append({"title": label, "items": items})

    _scan_grouped("companies", "公司档案")
    _scan_flat("industries", "行业概览")
    _scan_flat("concepts", "概念/主题")

    glossary = os.path.join(wiki_dir, "glossary.md")
    if os.path.isfile(glossary):
        sections.append({"title": "术语表", "items": [{"name": "A股术语表", "path": "glossary.md"}]})

    _scan_grouped("reports", "分析报告", name_transform=_report_name)
    _scan_root("未归类")

    return {"sections": sections}


def parse_index_entries(index_path: str) -> list[dict]:
    """解析 index.md 的分节链接，供结构化索引重建复用。"""
    entries = []
    current_section = ""
    try:
        with open(index_path, "r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if line.startswith("## "):
                    current_section = line[3:].strip()
                    continue
                match = _LINK_RE.match(line)
                if match:
                    entries.append({
                        "section": current_section,
                        "name": match.group(1).strip(),
                        "path": match.group(2).strip(),
                    })
    except (FileNotFoundError, PermissionError):
        pass
    return entries


_CODE_FENCE_RE = re.compile(r'```\w*\n(.*?)```', re.DOTALL)


def parse_wiki_page(file_path: str) -> dict:
    with open(file_path, "r", encoding="utf-8") as f:
        text = f.read()
    m = _CODE_FENCE_RE.search(text)
    if m and '---' in m.group(1):
        text = m.group(1)
    frontmatter = {}
    content = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            try:
                frontmatter = yaml.safe_load(parts[1]) or {}
            except yaml.YAMLError:
                frontmatter = {}
            content = parts[2].strip()
    wiki_links = _WIKI_LINK_RE.findall(content)
    return {
        "frontmatter": frontmatter,
        "content": content,
        "wiki_links": list(set(wiki_links)),
    }


def search_wiki(wiki_dir: str, query: str, max_results: int = 20) -> list[dict]:
    raise NotImplementedError("search_wiki was removed; use recall_wiki instead")


def _resolve_in_wiki(wiki_dir: str, rel_path: str) -> str | None:
    """把 wiki 相对路径解析为绝对路径；越出 wiki_dir 的返回 None。"""
    resolved = resolve_within(wiki_dir, os.path.join(wiki_dir, rel_path), strict=True)
    return str(resolved) if resolved is not None else None


def _read_page(wiki_dir: str, rel_path: str, max_chars: int) -> dict | None:
    full = _resolve_in_wiki(wiki_dir, rel_path)
    if full is None or not os.path.isfile(full):
        return None
    try:
        with open(full, "r", encoding="utf-8") as f:
            content = f.read()
    except (OSError, UnicodeDecodeError):
        return None

    # 从已读内容中提取 frontmatter.summary，避免重复文件 I/O
    summary = ""
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            try:
                fm = yaml.safe_load(parts[1]) or {}
                summary = fm.get("summary", "").strip()
            except yaml.YAMLError:
                pass

    if summary:
        return {
            "path": rel_path,
            "content": summary,
            "truncated": False,
            "source": "summary",
        }
    return {
        "path": rel_path,
        "content": content[:max_chars],
        "truncated": len(content) > max_chars,
        "source": "content",
    }


# ── BM25 召回引擎（wiki_recall 工具用） ──────────────

def _bm25_search(wiki_dir: str, keywords: list[str], top_k: int = 20,
                 k1: float = 1.5, b: float = 0.75) -> list[tuple[str, float]]:
    """子串 BM25 检索，返回 [(rel_path, score), ...] 按分数降序。

    tf = 关键词在原文中的子串出现次数（查询侧已是 LLM 预分词关键词，文档无需
    再分词），doc_len 以字符计。不建索引、无缓存，每次调用直接扫描全部文档，
    因此写入/覆盖/删除对后续召回立即可见。
    """
    docs = []  # (rel_path, casefolded_text)
    for root, dirs, files in os.walk(wiki_dir):
        dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(root, d))]
        for fname in files:
            if not fname.endswith(".md") or fname in ("index.md", "glossary.md"):
                continue
            fpath = os.path.join(root, fname)
            if os.path.islink(fpath):
                continue
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    text = f.read()
            except (OSError, UnicodeDecodeError):
                continue
            docs.append((os.path.relpath(fpath, wiki_dir), text.casefold()))

    n = len(docs)
    if n == 0:
        return []
    avgdl = sum(len(t) for _, t in docs) / n or 1.0

    scores = [0.0] * n
    for kw in keywords:
        kw = kw.casefold()
        if not kw:
            continue
        tfs = [text.count(kw) for _, text in docs]
        df = sum(1 for tf in tfs if tf > 0)
        if df == 0:
            continue
        idf = math.log((n - df + 0.5) / (df + 0.5) + 1.0)
        for i, tf in enumerate(tfs):
            if tf == 0:
                continue
            doc_len = len(docs[i][1])
            scores[i] += idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * doc_len / avgdl))

    results = [(docs[i][0], scores[i]) for i in range(n) if scores[i] > 0]
    results.sort(key=lambda x: x[1], reverse=True)
    return results[:top_k]


def recall_wiki(wiki_dir: str, query: str, max_chars: int = 500) -> list[dict]:
    """从本地 wiki 知识库召回相关页面（BM25 相关性排序）。

    Args:
        wiki_dir: wiki 根目录路径
        query: LLM 预分词的关键词（空格/逗号/顿号分隔），直接用于 BM25 检索
        max_chars: 单页返回的最大字符数

    Returns:
        [{"name", "path", "section", "content", "truncated", "score"}, ...]
    """
    keywords = [k.strip() for k in re.split(r'[\s,，、]+', query) if k.strip()]

    if not keywords:
        return []

    # ── BM25 排序检索 ──
    ranked = _bm25_search(wiki_dir, keywords)

    # ── 读取页面内容 ──
    pages = []
    for rel_path, score in ranked:
        page = _read_page(wiki_dir, rel_path, max_chars)
        if page is None:
            continue
        name = os.path.basename(rel_path).replace(".md", "")
        pages.append({
            **page,
            "name": name,
            "section": "",
            "score": round(score, 4),
        })

    return pages
