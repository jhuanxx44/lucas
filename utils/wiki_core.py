"""wiki 解析与召回核心：server（Wiki API）与 harness（wiki_recall 工具）共用。

自 server/services/wiki_parser.py 上移（M3），原模块保留为 re-export 兼容层。
"""
import math
import os
import re
from collections import Counter

import jieba
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

# 文档预处理：去 frontmatter 和 markdown 标记
_DOC_CLEAN_RE = re.compile(r'---.*?---|[#*`\[\]()>|!\-_{}=~]', re.DOTALL)

def _tokenize_doc(text: str) -> list[str]:
    """对文档正文分词，返回过滤后的 token 列表。

    同时保留原始专有名词（如"台积电"），防止 jieba 切分后与 LLM 关键词不匹配。
    """
    text = _DOC_CLEAN_RE.sub(' ', text)
    words = jieba.lcut(text)
    # 补充：从未清洗原文中提取专有名词（中英文连续字符 > 2）
    raw_terms = re.findall(r'[\u4e00-\u9fff]{3,}|[A-Za-z][A-Za-z0-9]{2,}', text)
    words.extend(raw_terms)
    stopwords = {'的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一',
                 '一个', '上', '也', '很', '到', '说', '要', '去', '你', '会', '着',
                 '没有', '看', '好', '自己', '这', '他', '她', '它', '们', '那', '些',
                 '所', '为', '所以', '因为', '但是', '然而', '可以', '这个', '那个',
                 '什么', '怎么', '如何', '哪个', '吗', '啊', '吧', '呢', '哦',
                 '与', '及', '等', '或', '被', '从', '对', '向', '以', '将',
                 '通过', '以及', '此外', '另外', '其中', '其他', '其它',
                 '进行', '使用', '需要', '可能', '已经', '还', '更', '最',
                 '之後', '之前', '之後', '之後', '關於', 'また', 'より'}
    return [w for w in words if len(w) >= 2 and w not in stopwords]


# 全局 BM25 索引缓存: {wiki_dir: BM25Index}
_bm25_cache: dict[str, dict] = {}


def _build_bm25_index(wiki_dir: str) -> dict:
    """构建 wiki_dir 下所有 .md 文档的 BM25 索引（带缓存）。"""
    if wiki_dir in _bm25_cache:
        return _bm25_cache[wiki_dir]

    doc_paths = []
    doc_tokens = []
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
            rel = os.path.relpath(fpath, wiki_dir)
            doc_paths.append(rel)
            doc_tokens.append(_tokenize_doc(text))

    N = len(doc_paths)
    if N == 0:
        _bm25_cache[wiki_dir] = {"N": 0}
        return _bm25_cache[wiki_dir]

    doc_lens = [len(t) for t in doc_tokens]
    avgdl = sum(doc_lens) / N

    df = {}
    for tokens in doc_tokens:
        for t in set(tokens):
            df[t] = df.get(t, 0) + 1
    idf = {}
    for t, d in df.items():
        idf[t] = math.log((N - d + 0.5) / (d + 0.5) + 1.0)

    index = {
        "N": N,
        "doc_paths": doc_paths,
        "doc_tokens": doc_tokens,
        "doc_lens": doc_lens,
        "avgdl": avgdl,
        "df": df,
        "idf": idf,
    }
    _bm25_cache[wiki_dir] = index
    return index


def _bm25_search(wiki_dir: str, keywords: list[str], top_k: int = 20,
                 k1: float = 1.5, b: float = 0.75) -> list[tuple[str, float]]:
    """BM25 检索，返回 [(rel_path, score), ...] 按分数降序。"""
    idx = _build_bm25_index(wiki_dir)
    if idx["N"] == 0:
        return []

    scores = [0.0] * idx["N"]
    for kw in keywords:
        if kw not in idx["idf"]:
            continue
        idf_val = idx["idf"][kw]
        for i in range(idx["N"]):
            tf = idx["doc_tokens"][i].count(kw)
            if tf == 0:
                continue
            doc_len = idx["doc_lens"][i]
            numerator = tf * (k1 + 1)
            denominator = tf + k1 * (1 - b + b * doc_len / idx["avgdl"])
            scores[i] += idf_val * numerator / denominator

    results = [(idx["doc_paths"][i], scores[i]) for i in range(idx["N"]) if scores[i] > 0]
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
