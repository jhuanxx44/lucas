import os
import glob
import logging
from typing import Optional

from agents.config import ResearcherConfig
from agents.models import Task, ResearchResult
from utils.llm_client import create_client
from utils.web_search import search as web_search
from utils.stock_data import get_stock_data

logger = logging.getLogger(__name__)

WIKI_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "wiki")


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


async def run_researcher(
    config: ResearcherConfig,
    task: Task,
    prior_results: list[ResearchResult] = None,
) -> ResearchResult:
    """执行单个研究员的分析任务"""
    client = create_client(model=config.model, system_prompt=config.system_prompt)

    # 搜索实时信息
    search_context = ""
    if config.enable_search:
        try:
            search_context = await web_search(f"{task.question} {config.expertise}", max_results=5)
        except Exception as e:
            logger.warning("[%s] 搜索失败: %s", config.name, e)

    # 拉取结构化市场数据
    market_data = ""
    if config.data_types:
        try:
            market_data = await get_stock_data(task.question, config.data_types)
        except Exception as e:
            logger.warning("[%s] 获取市场数据失败: %s", config.name, e)

    # 构建 prompt
    parts = [f"## 用户问题\n{task.question}"]
    if task.instruction:
        parts.append(f"## Manager 指令\n{task.instruction}")
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

    prompt = "\n\n".join(parts)
    prompt += "\n\n请给出你的专业分析。"

    logger.info("[%s] 开始分析 (model=%s)", config.name, config.model)
    text, usage = await client.chat(prompt=prompt, temperature=0.7, thinking_budget=8192)
    logger.info("[%s] 分析完成, tokens=%s", config.name, usage.total_tokens if usage else "N/A")

    return ResearchResult(
        researcher_id=config.id,
        researcher_name=config.name,
        model=config.model,
        content=text,
        token_usage=usage,
    )
