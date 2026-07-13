import os
import re
import glob
import logging
from typing import AsyncGenerator

import jieba
import jieba.posseg as pseg

from agents.config import ResearcherConfig
from agents.models import Task, ResearchResult
from utils.llm_client import create_client
from utils.web_search import search as web_search
from utils.stock_data import get_stock_data

logger = logging.getLogger(__name__)

_MD_LINK_RE = re.compile(r'\[([^\]]*)\]\((https?://[^\s\)]+)\)')

# ── 中文停用词 ──
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


def _extract_urls_from_search(search_text: str) -> list[dict]:
    """从搜索结果文本中提取所有 URL 及标题"""
    urls = []
    seen = set()
    for title, url in _MD_LINK_RE.findall(search_text):
        if url not in seen:
            seen.add(url)
            urls.append({"title": title.strip(), "url": url.strip()})
    return urls


def _extract_keywords(question: str) -> list[str]:
    """用 jieba 分词 + 词性过滤提取关键词，同时保留原始 question 中的连续中文片段。"""
    keywords = []
    # 英文/数字 token（股票代码等）
    for token in re.findall(r"[A-Za-z0-9]+", question):
        if len(token) >= 1:
            keywords.append(token.lower())
    # jieba 分词 + 词性过滤：名词、动词、地名、机构名
    for word, flag in pseg.cut(question):
        if len(word) < 2:
            continue
        if word in _STOP_WORDS:
            continue
        if flag.startswith(("n", "v", "ns", "nt", "nz")):
            keywords.append(word)
    # fallback: 提取所有连续中文字段（长度 2-8），防止 jieba 将股票简称等专有名词切碎
    for chunk in re.findall(r"[一-鿿]{2,8}", question):
        if chunk not in _STOP_WORDS and len(chunk) >= 2:
            keywords.append(chunk)
    # 去重保序
    seen = set()
    deduped = []
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            deduped.append(kw)
    return deduped


def _parse_wiki_index(index_path: str) -> list[dict]:
    """解析 index.md 的 # Section → - [name](path) 结构。

    返回: [{"section": "公司 · 电子", "name": "沪电股份", "path": "companies/电子/沪电股份.md"}, ...]
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
                elif line.startswith("- [") and "](" in line:
                    m = re.match(r"- \[(.+?)\]\((.+?)\)", line)
                    if m:
                        entries.append({
                            "section": current_section,
                            "name": m.group(1).strip(),
                            "path": m.group(2).strip(),
                        })
    except (FileNotFoundError, PermissionError):
        pass
    return entries


def _find_wiki_context(question: str, wiki_dir: str) -> str:
    """从 wiki/ 中找到可能相关的页面内容作为上下文。

    策略：
    1. 优先用关键词匹配 index.md 条目（条目名 + 分类名）
    2. fallback 到 glob 遍历 .md 文件，按关键词命中数评分
    3. 返回 top 3 页面，每页截断至 3000 字符
    """
    keywords = _extract_keywords(question)
    if not keywords:
        return ""

    # ── Step 1: 优先匹配 index.md ──
    index_path = os.path.join(wiki_dir, "index.md")
    index_entries = _parse_wiki_index(index_path)
    index_hits: list[tuple[int, dict]] = []
    for entry in index_entries:
        score = 0
        search_text = f"{entry['name']} {entry['section']}"
        for kw in keywords:
            if kw in search_text:
                score += 1
        if score > 0:
            index_hits.append((score, entry))
    index_hits.sort(key=lambda x: x[0], reverse=True)

    context_parts = []
    seen_paths = set()
    for _, entry in index_hits[:3]:
        page_path = os.path.join(wiki_dir, entry["path"])
        norm = os.path.normpath(page_path)
        if norm in seen_paths:
            continue
        seen_paths.add(norm)
        try:
            with open(norm, "r", encoding="utf-8") as f:
                content = f.read()
            context_parts.append(f"--- {entry['name']} ({entry['section']}) ---\n{content[:3000]}")
        except Exception:
            continue

    # ── Step 2: glob fallback ──
    if len(context_parts) < 3:
        scored = []
        for md_path in glob.glob(os.path.join(wiki_dir, "**", "*.md"), recursive=True):
            if "index.md" in md_path or "glossary.md" in md_path:
                continue
            norm = os.path.normpath(md_path)
            if norm in seen_paths:
                continue
            try:
                with open(norm, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception:
                continue
            basename = os.path.basename(md_path)
            name_no_ext = basename.replace(".md", "")
            # 评分：文件名命中 × 3，内容前 2000 字符命中 × 1
            score = 0
            for kw in keywords:
                if kw in name_no_ext:
                    score += 3
                if kw in content[:2000]:
                    score += 1
            if score > 0:
                scored.append((score, basename, content))
        scored.sort(key=lambda x: x[0], reverse=True)

        remaining = 3 - len(context_parts)
        for _, basename, content in scored[:remaining]:
            context_parts.append(f"--- {basename} ---\n{content[:3000]}")

    if not context_parts:
        return ""
    return "\n\n".join(context_parts)


async def _build_prompt(config: ResearcherConfig, task: Task, prior_results=None) -> str:
    search_context = ""
    search_urls = []
    if config.enable_search:
        try:
            search_context = await web_search(f"{task.question} {config.expertise}", max_results=5)
            if search_context:
                search_urls = _extract_urls_from_search(search_context)
        except Exception as e:
            logger.warning("[%s] 搜索失败: %s", config.name, e)

    market_data = ""
    if config.data_types:
        try:
            market_data = await get_stock_data(task.question, config.data_types)
        except Exception as e:
            logger.warning("[%s] 获取市场数据失败: %s", config.name, e)

    # 优先使用 per-researcher 差异化子任务
    rt = task.get_researcher_task(config.id) if hasattr(task, 'get_researcher_task') else None

    parts = [f"## 用户问题\n{task.question}"]
    if rt and rt.sub_question:
        parts.append(f"## 你需要回答的子问题\n{rt.sub_question}")
    if rt and rt.focus:
        parts.append(f"## 聚焦维度（只分析这些）\n{rt.focus}")
    if rt and rt.avoid:
        parts.append(f"## 不要涉及（属于其他研究员的领域）\n{rt.avoid}")
    if task.instruction:
        parts.append(f"## Manager 补充指令\n{task.instruction}")
    if market_data:
        parts.append(f"## 市场数据（结构化）\n{market_data}")
    if search_context:
        parts.append(f"## 网络搜索参考（实时信息）\n{search_context}")
    if task.context:
        parts.append(f"## 知识库参考\n{task.context}")
    if prior_results:
        parts.append("## 前序研究员的分析（供参考）")
        for pr in prior_results:
            parts.append(f"### {pr.researcher_name}（{pr.model}）\n{pr.content}")

    prompt = "\n\n".join(parts) + "\n\n请给出你的专业分析。"
    if search_urls:
        prompt += (
            "\n\n**重要：参考资料引用规则**"
            "\n- 在分析正文中引用信息时，用 Markdown 链接标注来源，如 [来源标题](URL)"
            "\n- 在分析末尾添加 `## 参考资料` 部分，列出你实际引用的链接"
            "\n- 只能使用上方「网络搜索参考」中提供的 URL，严禁编造或猜测链接"
            "\n- 如果搜索结果中没有相关链接，不要伪造，直接省略即可"
        )
    return prompt, search_urls, market_data


async def run_researcher_stream(
    config: ResearcherConfig,
    task: Task,
    prior_results: list[ResearchResult] = None,
) -> AsyncGenerator[dict, None]:
    client = create_client(model=config.model, system_prompt=config.system_prompt)
    prompt, search_urls, market_data = await _build_prompt(config, task, prior_results)

    yield {"event": "_meta", "data": {"id": config.id, "source_urls": search_urls, "market_data": market_data}}

    logger.info("[%s] 开始流式分析 (model=%s)", config.name, config.model)
    async for chunk in client.chat_stream(prompt=prompt, temperature=0.7):
        yield {"event": "researcher_chunk", "data": {"id": config.id, "text": chunk}}
