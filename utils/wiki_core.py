"""wiki 解析与召回核心：server（Wiki API）与 harness（wiki_recall 工具）共用。

自 server/services/wiki_parser.py 上移（M3），原模块保留为 re-export 兼容层。
"""
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
    results = []
    for root, _, files in os.walk(wiki_dir):
        for fname in files:
            if not fname.endswith(".md") or fname == "index.md":
                continue
            fpath = os.path.join(root, fname)
            rel = os.path.relpath(fpath, wiki_dir)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    content = f.read(4000)
            except Exception:
                continue
            name = fname.replace(".md", "")
            if query in name or query in content:
                snippet_idx = content.find(query)
                snippet = ""
                if snippet_idx >= 0:
                    start = max(0, snippet_idx - 40)
                    snippet = content[start:snippet_idx + len(query) + 60].replace("\n", " ")
                results.append({"name": name, "path": rel, "snippet": snippet})
            if len(results) >= max_results:
                break
    return results


# ── 索引优先召回（wiki_recall 工具用） ─────────────────

# 中文停用词（关键词提取时过滤）
_STOP_WORDS = frozenset({
    "的", "了", "是", "在", "我", "你", "他", "她", "它", "们",
    "这", "那", "吗", "呢", "吧", "啊", "哦", "嗯",
    "和", "与", "或", "但", "而", "及", "向", "对", "以", "被", "把", "从", "到",
    "让", "请", "帮", "用", "给", "为",
    "因为", "所以", "如果", "虽然", "可以", "应该", "需要",
    "已经", "正在", "将要",
    "也", "都", "就", "才", "又", "再", "还",
    "很", "非常", "最", "更", "越",
    "不", "没", "没有",
    "什么", "怎么", "怎样", "如何", "为什么", "哪里", "哪个",
    "一个", "一下", "一些", "这个", "那个", "这种", "那种",
    "分析", "调研", "看看", "研究", "查询", "请问", "帮忙",
})

_INDEX_ENTRY_RE = re.compile(r"- \[(.+?)\]\((.+?)\)")


def extract_keywords(query: str) -> list[str]:
    """jieba 分词 + 词性过滤提取关键词；英文/数字 token 原样保留。"""
    import jieba.posseg as pseg

    keywords = []
    for token in re.findall(r"[A-Za-z0-9]+", query):
        keywords.append(token.lower())
    for word, flag in pseg.cut(query):
        if len(word) < 2 or word in _STOP_WORDS:
            continue
        if flag.startswith(("n", "v", "ns", "nt", "nz")):
            keywords.append(word)
    seen = set()
    deduped = []
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            deduped.append(kw)
    return deduped


def parse_index_entries(index_path: str) -> list[dict]:
    """解析 index.md 的 `## Section` → `- [name](path)` 结构。

    返回: [{"section": "公司档案 · 电子", "name": "沪电股份", "path": "companies/电子/沪电股份.md"}, ...]
    """
    entries = []
    current_section = ""
    try:
        with open(index_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if line.startswith("## "):
                    current_section = line[3:].strip()
                elif line.startswith("- ["):
                    m = _INDEX_ENTRY_RE.match(line)
                    if m:
                        entries.append({
                            "section": current_section,
                            "name": m.group(1).strip(),
                            "path": m.group(2).strip(),
                        })
    except (FileNotFoundError, PermissionError):
        pass
    return entries


def _resolve_in_wiki(wiki_dir: str, rel_path: str) -> str | None:
    """把 wiki 相对路径解析为绝对路径；越出 wiki_dir 的返回 None（防索引条目逃逸）。"""
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
    return {
        "path": rel_path,
        "content": content[:max_chars],
        "truncated": len(content) > max_chars,
    }


def recall_wiki(wiki_dir: str, query: str, max_chars: int = 3000) -> list[dict]:
    """索引优先召回：先 index.md 条目关键词匹配，不足再全文子串 fallback。

    返回所有命中的页面: [{"name", "path", "section", "content", "truncated"}, ...]，
    单页 content 截断至 max_chars。
    """
    keywords = extract_keywords(query)
    if not keywords:
        return []

    pages: list[dict] = []
    seen: set[str] = set()

    # ── Step 1: 索引条目匹配（条目名 + 分类名） ──
    index_path = _resolve_in_wiki(wiki_dir, "index.md")
    index_entries = parse_index_entries(index_path) if index_path is not None else []
    scored_entries = []
    for entry in index_entries:
        search_text = f"{entry['name']} {entry['section']}"
        score = sum(1 for kw in keywords if kw in search_text)
        if entry["name"] and entry["name"] in query:
            score += 2  # 条目名直接出现在查询里，强信号且不依赖分词结果
        if score > 0:
            scored_entries.append((score, entry))
    scored_entries.sort(key=lambda x: x[0], reverse=True)

    for _, entry in scored_entries:
        page = _read_page(wiki_dir, entry["path"], max_chars)
        if page is None:
            continue
        full = _resolve_in_wiki(wiki_dir, entry["path"])
        if full in seen:
            continue
        seen.add(full)
        pages.append({**page, "name": entry["name"], "section": entry["section"]})

    # ── Step 2: 全文 fallback（补充索引未覆盖的页面） ──
    scored_files = []
    for root, dirs, files in os.walk(wiki_dir):
        dirs[:] = [name for name in dirs
                   if not os.path.islink(os.path.join(root, name))]
        for fname in files:
            if not fname.endswith(".md") or fname in ("index.md", "glossary.md"):
                continue
            candidate = os.path.join(root, fname)
            if os.path.islink(candidate):
                continue
            rel = os.path.relpath(candidate, wiki_dir)
            full = _resolve_in_wiki(wiki_dir, rel)
            if full is None or full in seen:
                continue
            try:
                with open(full, "r", encoding="utf-8") as f:
                    content = f.read()
            except (OSError, UnicodeDecodeError):
                continue
            name = fname.replace(".md", "")
            # 评分：文件名命中 × 3，内容前 2000 字符命中 × 1
            score = 0
            for kw in keywords:
                if kw in name:
                    score += 3
                if kw in content[:2000]:
                    score += 1
            if score > 0:
                scored_files.append((score, name, rel, content))
    scored_files.sort(key=lambda x: x[0], reverse=True)

    for _, name, rel, content in scored_files:
        resolved = _resolve_in_wiki(wiki_dir, rel)
        if resolved is None:
            continue
        seen.add(resolved)
        pages.append({
            "name": name,
            "path": rel,
            "section": "",
            "content": content[:max_chars],
            "truncated": len(content) > max_chars,
        })

    return pages
