import os
import re
import glob
import logging
from typing import AsyncGenerator, Optional

from agents.config import ResearcherConfig
from agents.models import Task, ResearchResult
from utils.llm_client import create_client
from utils.web_search import search as web_search
from utils.stock_data import get_stock_data

logger = logging.getLogger(__name__)

WIKI_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "wiki")

_MD_LINK_RE = re.compile(r'\[([^\]]*)\]\((https?://[^\s\)]+)\)')


def _extract_urls_from_search(search_text: str) -> list[dict]:
    """从搜索结果文本中提取所有 URL 及标题"""
    urls = []
    seen = set()
    for title, url in _MD_LINK_RE.findall(search_text):
        if url not in seen:
            seen.add(url)
            urls.append({"title": title.strip(), "url": url.strip()})
    return urls


def _find_wiki_context(question: str) -> str:
    """从 wiki/ 中找到可能相关的页面内容作为上下文"""
    context_parts = []
    for md_path in glob.glob(os.path.join(WIKI_DIR, "**", "*.md"), recursive=True):
        if "index.md" in md_path or "glossary.md" in md_path:
            continue
        try:
            with open(md_path, "r", encoding="utf-8") as f:
                content = f.read()
            # 简单匹配：文件名或内容中包含问题关键词
            basename = os.path.basename(md_path)
            # 取问题中的关键词（去掉常见停用词）
            for char in question:
                if char in basename or char in content[:500]:
                    context_parts.append(f"--- {basename} ---\n{content[:2000]}")
                    break
        except Exception:
            continue
    if not context_parts:
        return ""
    return "\n\n".join(context_parts[:3])


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


async def run_researcher(
    config: ResearcherConfig,
    task: Task,
    prior_results: list[ResearchResult] = None,
) -> ResearchResult:
    """执行单个研究员的分析任务"""
    client = create_client(model=config.model, system_prompt=config.system_prompt)
    prompt, search_urls, market_data = await _build_prompt(config, task, prior_results)

    logger.info("[%s] 开始分析 (model=%s)", config.name, config.model)
    text, usage = await client.chat(prompt=prompt, temperature=0.7, thinking_budget=8192)
    logger.info("[%s] 分析完成, tokens=%s", config.name, usage.total_tokens if usage else "N/A")

    return ResearchResult(
        researcher_id=config.id,
        researcher_name=config.name,
        model=config.model,
        content=text,
        token_usage=usage,
        source_urls=search_urls,
        market_data=market_data,
    )


async def run_researcher_stream(
    config: ResearcherConfig,
    task: Task,
    prior_results: list[ResearchResult] = None,
) -> AsyncGenerator[dict, None]:
    """执行单个研究员的分析任务（流式版本），yield SSE event dicts"""
    client = create_client(model=config.model, system_prompt=config.system_prompt)
    prompt, _, _ = await _build_prompt(config, task, prior_results)

    logger.info("[%s] 开始流式分析 (model=%s)", config.name, config.model)
    async for chunk in client.chat_stream(prompt=prompt, temperature=0.7):
        yield {"event": "researcher_chunk", "data": {"id": config.id, "text": chunk}}
