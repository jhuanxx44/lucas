import asyncio
import logging
from typing import AsyncGenerator

from agents.config import AgentsConfig
from agents.models import Task, ResearchResult
from agents import researcher as researcher_module
from agents.researcher import run_researcher_stream
from utils.verify import verify_result

logger = logging.getLogger(__name__)


class ResearchService:
    """研究执行服务：负责跑研究员、验证结果、汇总输出。"""

    def __init__(self, config: AgentsConfig, client, prompt_loader):
        self.config = config
        self.client = client
        self._load_prompt = prompt_loader

    async def run_parallel(self, task: Task, max_concurrency: int = 2) -> list[ResearchResult]:
        sem = asyncio.Semaphore(max_concurrency)

        async def _run_with_sem(rc):
            async with sem:
                return await researcher_module.run_researcher(rc, task)

        coros = []
        for rid in task.researcher_ids:
            rc = self.config.get_researcher(rid)
            if rc:
                coros.append(_run_with_sem(rc))
        return list(await asyncio.gather(*coros))

    async def run_serial(self, task: Task) -> list[ResearchResult]:
        results = []
        for rid in task.researcher_ids:
            rc = self.config.get_researcher(rid)
            if rc:
                result = await researcher_module.run_researcher(rc, task, prior_results=results)
                results.append(result)
        return results

    async def run(self, task: Task, on_status=None) -> list[ResearchResult]:
        def status(msg):
            if on_status:
                on_status(msg)

        if task.mode == "serial":
            status("串行执行中...")
            results = await self.run_serial(task)
        else:
            status("并行执行中...")
            results = await self.run_parallel(task)

        for r in results:
            status(f"✓ {r.researcher_name} 完成")

        status("正在验证研究结果...")
        await asyncio.gather(*(verify_result(r) for r in results))
        for r in results:
            if r.verification and not r.verification.passed:
                status(f"⚠ {r.researcher_name}: {r.verification.error_count} 个数据问题, 置信度={r.confidence}")
            else:
                status(f"✓ {r.researcher_name} 验证通过")

        return results

    async def run_stream(self, task: Task) -> AsyncGenerator[dict, None]:
        """流式执行研究员，yield SSE 事件，最后 yield _results 事件携带结果列表。"""
        researcher_configs = [
            rc for rid in task.researcher_ids
            if (rc := self.config.get_researcher(rid)) is not None
        ]

        queue: asyncio.Queue = asyncio.Queue()
        results: list[ResearchResult] = []

        async def _stream_one(rc, prior: list[ResearchResult] | None = None):
            full_text = []
            try:
                async for evt in run_researcher_stream(rc, task, prior_results=prior):
                    await queue.put(evt)
                    if evt["event"] == "researcher_chunk":
                        full_text.append(evt["data"]["text"])
            except Exception as e:
                logger.error("[%s] 研究员异常: %s", rc.name, e)
                await queue.put({"event": "researcher_error", "data": {"id": rc.id, "message": str(e)}})
            result = ResearchResult(
                researcher_id=rc.id,
                researcher_name=rc.name,
                model=rc.model,
                content="".join(full_text) or "[分析失败]",
                token_usage=None,
            )
            await queue.put({"event": "_result", "data": {"result": result}})
            await queue.put({"event": "researcher_done", "data": {"id": rc.id}})

        if task.mode == "serial":
            async def _run():
                serial_prior: list[ResearchResult] = []
                for rc in researcher_configs:
                    await queue.put({"event": "researcher_start", "data": {"id": rc.id, "name": rc.name}})
                    await _stream_one(rc, prior=serial_prior if serial_prior else None)
                    if results:
                        serial_prior.append(results[-1])
                await queue.put({"event": "_done", "data": {}})
        else:
            async def _run():
                for rc in researcher_configs:
                    await queue.put({"event": "researcher_start", "data": {"id": rc.id, "name": rc.name}})
                sem = asyncio.Semaphore(2)
                async def _with_sem(rc_inner):
                    async with sem:
                        await _stream_one(rc_inner)
                await asyncio.gather(*[_with_sem(rc) for rc in researcher_configs])
                await queue.put({"event": "_done", "data": {}})

        runner = asyncio.create_task(_run())

        while True:
            evt = await queue.get()
            if evt["event"] == "_result":
                results.append(evt["data"]["result"])
                continue
            if evt["event"] == "_done":
                break
            yield evt

        await runner
        yield {"event": "_results", "data": {"results": results}}

    async def synthesize(self, question: str, results: list[ResearchResult]) -> str:
        parts = []
        for r in results:
            section = f"### {r.researcher_name}（{r.model}）\n{r.content}"
            if r.verification and r.verification.issues:
                warnings = [i for i in r.verification.issues if i.severity in ("error", "warning")]
                if warnings:
                    section += "\n\n**⚠ 数据验证提示：**\n" + "\n".join(f"- {i.message}" for i in warnings)
            parts.append(section)
        results_text = "\n\n".join(parts)
        prompt = self._load_prompt("synthesis").format(
            question=question,
            results=results_text,
        )
        text, _ = await self.client.chat(prompt=prompt, temperature=0.5)
        return text
