import os
import re
import yaml

_LINK_RE = re.compile(r'-\s+\[([^\]]+)\]\(([^)]+)\)(?:\s*—\s*(.+))?')
_WIKI_LINK_RE = re.compile(r'\[\[([^\]]+)\]\]')
_SECTION_RE = re.compile(r'^##\s+(.+)$', re.MULTILINE)


def parse_wiki_index(wiki_dir: str) -> dict:
    index_path = os.path.join(wiki_dir, "index.md")
    with open(index_path, "r", encoding="utf-8") as f:
        text = f.read()
    sections = []
    parts = _SECTION_RE.split(text)
    for i in range(1, len(parts), 2):
        title = parts[i].strip()
        body = parts[i + 1] if i + 1 < len(parts) else ""
        items = []
        for m in _LINK_RE.finditer(body):
            name, path, desc = m.group(1), m.group(2), m.group(3)
            item = {"name": name, "path": path}
            if desc:
                item["description"] = desc.strip()
            items.append(item)
        if items:
            sections.append({"title": title, "items": items})
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
            frontmatter = yaml.safe_load(parts[1]) or {}
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
