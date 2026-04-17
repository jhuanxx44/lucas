import asyncio
import json
import logging
import os
from datetime import date
from typing import Optional

from agents.config import AgentsConfig
from agents.models import Task, ResearchResult, ManagerReport
from agents.researcher import run_researcher, _find_wiki_context
from utils.llm_client import create_client

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))

DISPATCH_PROMPT_TEMPLATE = """你是 Manager，需要根据用户问题决定如何派发任务给研究员。

## 可用研究员
{researchers_desc}

## 用户问题
{question}

请返回 JSON，格式：
{{
  "researcher_ids": ["要派发的研究员id列表"],
  "mode": "parallel 或 serial",
  "instruction": "给研究员的统一指令（补充说明、分析重点等）"
}}

规则：
- 根据问题性质选择合适的研究员，不必每次都全选
- 如果问题需要多角度交叉验证，选多个研究员
- 如果后续研究员需要参考前序结果（如先基本面再技术面），用 serial
- 简单问题可以只派一个研究员"""

SYNTHESIS_PROMPT_TEMPLATE = """你是 Manager，需要汇总各研究员的分析结果。

## 用户原始问题
{question}

## 各研究员分析
{results}

请给出综合分析报告，包含：
1. **综合结论** — 一段话总结
2. **各方观点** — 简要列出每位研究员的核心观点
3. **一致之处** — 研究员们达成共识的部分
4. **分歧之处** — 研究员们意见不同的部分（如有）
5. **综合建议** — 你作为 Manager 的最终建议"""


class Manager:
    def __init__(self, config: AgentsConfig):
        self.config = config
        self.client = create_client(
            model=config.manager.model,
            system_prompt=config.manager.system_prompt,
        )

    async def _dispatch(self, question: str) -> Task:
        """分析用户意图，决定派发策略"""
        researchers_desc = "\n".join(
            f"- id: {r.id}, 名称: {r.name}, 擅长: {r.expertise}"
            for r in self.config.researchers
        )
        prompt = DISPATCH_PROMPT_TEMPLATE.format(
            researchers_desc=researchers_desc,
            question=question,
        )
        text, _ = await self.client.chat(
            prompt=prompt,
            response_mime_type="application/json",
            temperature=0.3,
        )
        try:
            plan = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Manager dispatch JSON 解析失败，使用全部研究员")
            plan = {
                "researcher_ids": self.config.list_researcher_ids(),
                "mode": "parallel",
                "instruction": "",
            }

        # 验证 researcher_ids
        valid_ids = set(self.config.list_researcher_ids())
        researcher_ids = [rid for rid in plan.get("researcher_ids", []) if rid in valid_ids]
        if not researcher_ids:
            researcher_ids = list(valid_ids)

        context = _find_wiki_context(question)

        return Task(
            question=question,
            instruction=plan.get("instruction", ""),
            researcher_ids=researcher_ids,
            mode=plan.get("mode", "parallel"),
            context=context,
        )

    async def _run_parallel(self, task: Task, max_concurrency: int = 2) -> list[ResearchResult]:
        """并行执行所有研究员（限制并发数避免代理限流）"""
        sem = asyncio.Semaphore(max_concurrency)

        async def _run_with_sem(rc):
            async with sem:
                return await run_researcher(rc, task)

        coros = []
        for rid in task.researcher_ids:
            rc = self.config.get_researcher(rid)
            if rc:
                coros.append(_run_with_sem(rc))
        return list(await asyncio.gather(*coros))

    async def _run_serial(self, task: Task) -> list[ResearchResult]:
        """串行执行，后续研究员可看到前序结果"""
        results = []
        for rid in task.researcher_ids:
            rc = self.config.get_researcher(rid)
            if rc:
                result = await run_researcher(rc, task, prior_results=results)
                results.append(result)
        return results

    async def _synthesize(self, question: str, results: list[ResearchResult]) -> str:
        """汇总各研究员结果"""
        results_text = "\n\n".join(
            f"### {r.researcher_name}（{r.model}）\n{r.content}"
            for r in results
        )
        prompt = SYNTHESIS_PROMPT_TEMPLATE.format(
            question=question,
            results=results_text,
        )
        text, _ = await self.client.chat(prompt=prompt, temperature=0.5)
        return text

    async def analyze(self, question: str, on_status=None) -> ManagerReport:
        """
        完整分析流程：派发 → 执行 → 汇总

        Args:
            question: 用户问题
            on_status: 状态回调 fn(msg: str)，用于 CLI 显示进度
        """
        def status(msg):
            if on_status:
                on_status(msg)

        # 1. 派发
        status("正在分析问题，制定研究计划...")
        task = await self._dispatch(question)
        names = [self.config.get_researcher(rid).name for rid in task.researcher_ids
                 if self.config.get_researcher(rid)]
        status(f"派发给: {', '.join(names)} | 模式: {task.mode}")
        if task.instruction:
            status(f"指令: {task.instruction}")

        # 2. 执行
        if task.mode == "serial":
            status("串行执行中...")
            results = await self._run_serial(task)
        else:
            status("并行执行中...")
            results = await self._run_parallel(task)

        for r in results:
            status(f"✓ {r.researcher_name} 完成")

        # 3. 汇总
        if len(results) > 1:
            status("正在汇总分析结果...")
            synthesis = await self._synthesize(question, results)
        elif len(results) == 1:
            synthesis = results[0].content
        else:
            synthesis = "没有研究员返回结果。"

        total_tokens = sum(r.token_usage.total_tokens for r in results if r.token_usage)

        report = ManagerReport(
            question=question,
            results=results,
            synthesis=synthesis,
            total_tokens=total_tokens,
        )

        # 4. 归档
        status("正在归档分析结果...")
        self._archive(report)

        return report

    def _make_slug(self, question: str) -> str:
        """从问题生成简短文件名片段"""
        slug = question.replace(" ", "_").replace("/", "_").replace("?", "").replace("？", "")
        return slug[:40]

    def _archive(self, report: ManagerReport):
        """归档：研究员原始分析 → raw/reports/，Manager 汇总 → wiki/reports/"""
        today = date.today().isoformat()
        slug = self._make_slug(report.question)

        # raw/reports/ — 每个研究员的原始分析
        raw_dir = os.path.join(_PROJECT_ROOT, "raw", "reports", today)
        os.makedirs(raw_dir, exist_ok=True)
        for r in report.results:
            filename = f"{r.researcher_id}_{slug}.md"
            path = os.path.join(raw_dir, filename)
            content = (
                f"---\n"
                f"question: {report.question}\n"
                f"researcher: {r.researcher_name}\n"
                f"model: {r.model}\n"
                f"date: {today}\n"
                f"---\n\n"
                f"{r.content}\n"
            )
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)

        # wiki/reports/ — Manager 汇总报告
        wiki_dir = os.path.join(_PROJECT_ROOT, "wiki", "reports")
        os.makedirs(wiki_dir, exist_ok=True)
        wiki_filename = f"{today}_{slug}.md"
        wiki_path = os.path.join(wiki_dir, wiki_filename)

        sources = "\n".join(
            f"  - raw/reports/{today}/{r.researcher_id}_{slug}.md"
            for r in report.results
        )
        researchers_list = ", ".join(
            f"{r.researcher_name}({r.model})" for r in report.results
        )
        wiki_content = (
            f"---\n"
            f"title: {report.question}\n"
            f"type: report\n"
            f"created: {today}\n"
            f"updated: {today}\n"
            f"sources:\n{sources}\n"
            f"researchers: {researchers_list}\n"
            f"tags: [分析报告]\n"
            f"confidence: medium\n"
            f"---\n\n"
            f"{report.synthesis}\n"
        )
        with open(wiki_path, "w", encoding="utf-8") as f:
            f.write(wiki_content)

        # 更新 wiki/index.md
        self._update_index(wiki_filename, report.question)

        logger.info("归档完成: raw/reports/%s/ + wiki/reports/%s", today, wiki_filename)

    def _update_index(self, wiki_filename: str, question: str):
        index_path = os.path.join(_PROJECT_ROOT, "wiki", "index.md")
        entry = f"- [{question}](reports/{wiki_filename})"

        try:
            with open(index_path, "r", encoding="utf-8") as f:
                content = f.read()
        except FileNotFoundError:
            content = "# Lucas A股股市 Wiki 索引\n"

        if wiki_filename in content:
            return

        section_header = "## 分析报告"
        if section_header not in content:
            content = content.rstrip() + f"\n\n{section_header}\n{entry}\n"
        else:
            content = content.replace(section_header, f"{section_header}\n{entry}", 1)

        with open(index_path, "w", encoding="utf-8") as f:
            f.write(content)
