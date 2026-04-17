import asyncio
import json
import logging
from typing import Optional

from agents.config import AgentsConfig
from agents.models import Task, ResearchResult, ManagerReport
from agents.researcher import run_researcher, _find_wiki_context
from utils.llm_client import create_client

logger = logging.getLogger(__name__)

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

        return ManagerReport(
            question=question,
            results=results,
            synthesis=synthesis,
            total_tokens=total_tokens,
        )
