import os
import re
import yaml

_LINK_RE = re.compile(r'-\s+\[([^\]]+)\]\(([^)]+)\)(?:\s*—\s*(.+))?')
_WIKI_LINK_RE = re.compile(r'\[\[([^\]]+)\]\]')
_SECTION_RE = re.compile(r'^##\s+(.+)$', re.MULTILINE)


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

    _scan_grouped("companies", "公司档案")
    _scan_flat("industries", "行业概览")
    _scan_flat("concepts", "概念/主题")

    glossary = os.path.join(wiki_dir, "glossary.md")
    if os.path.isfile(glossary):
        sections.append({"title": "术语表", "items": [{"name": "A股术语表", "path": "glossary.md"}]})

    _scan_grouped("reports", "分析报告", name_transform=_report_name)

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
