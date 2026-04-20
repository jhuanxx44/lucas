import asyncio
import glob
import json
import logging
import os
from datetime import date
from typing import AsyncGenerator, Optional

from agents.config import AgentsConfig
from agents.models import Task, ResearchResult, ManagerReport
from agents.memory import ManagerMemory
from agents.researcher import run_researcher, run_researcher_stream, _find_wiki_context
from agents.tools import get_tools_description, execute_tool
from utils.llm_client import create_client
from utils.verify import verify_result
from utils.json_extract import extract_json

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
_WIKI_DIR = os.path.join(_PROJECT_ROOT, "wiki")
_PROMPTS_DIR = os.path.join(_PROJECT_ROOT, "prompts")
_MEMORY_DIR = os.path.join(_PROJECT_ROOT, "memory")

DISPATCH_PROMPT_TEMPLATE = """你是 Lucas，需要根据用户问题决定如何处理。

## 可用研究员
{researchers_desc}

## 用户问题
{question}

## 知识库已有内容
{wiki_context}

## 记忆
{memory_context}

**重要：只返回 JSON，不要其他任何文字。**判断用户意图：

1. 如果不需要派发研究员（闲聊、问候、查询历史、询问文件位置、基于知识库回答等），返回：
{{
  "action": "direct"
}}

2. 如果需要研究员进行新的研究分析（知识库没有相关内容，或用户明确要求最新数据/深度分析），返回：
{{
  "action": "research",
  "researcher_ids": ["要派发的研究员id列表"],
  "mode": "parallel 或 serial",
  "instruction": "给研究员的统一指令（补充说明、分析重点等）"
}}

3. 如果用户要求编译 raw/ 中的原始资料到 wiki（如"编译 raw/xxx.md"、"处理这份研报"、"整理原始资料"、"更新知识库"），返回：
{{
  "action": "compile",
  "sources": ["raw/路径/文件.md"],
  "scope": "all 或 specific"
}}

规则：
- 大多数非研究类问题用 direct（Lucas 会自己判断是否需要查文件）
- 只有需要研究员做深度分析时才用 research
- "编译"、"整理 wiki"、"处理研报"、"更新知识库" 等指令用 compile
- 结合对话历史理解用户意图（如"继续分析"指的是上一轮的主题）
- 根据问题性质选择合适的研究员，不必每次都全选
- 如果问题需要多角度交叉验证，选多个研究员
- 如果后续研究员需要参考前序结果（如先基本面再技术面），用 serial
- 简单问题可以只派一个研究员"""

SYNTHESIS_PROMPT_TEMPLATE = """你是 Lucas，需要批判性地综合各研究员的分析结果。

你收到了来自不同专业视角的研究员分析：
- **基本面分析师**：关注财务数据、估值模型、公司基本面
- **技术面分析师**：关注K线形态、技术指标、量价关系
- **宏观策略师**：关注宏观经济、政策环境、行业趋势

## 用户原始问题
{question}

## 各研究员分析
{results}

---

**你的任务不是简单拼接这些观点，而是批判性地综合它们。**

请按以下步骤进行深度分析：

### 1. 识别共识（Consensus）
三位研究员在哪些核心判断上达成一致？这些共识点通常更可靠，因为它们跨越了不同分析框架的验证。

### 2. 识别分歧（Divergence）
在哪些关键问题上存在矛盾或不同结论？分析分歧的根源：
- 是数据解读差异？
- 是时间维度不同（短期 vs 长期）？
- 是风险偏好不同？

### 3. 评估偏差（Bias Assessment）
批判性评估每位研究员可能的视角局限：
- 基本面分析师可能过度关注财报数字，忽视市场情绪
- 技术面分析师可能过度依赖历史形态，忽视基本面变化
- 宏观策略师可能过于宏观，忽视个股特质

### 4. 交叉验证（Cross-Validation）
不同视角的结论是否相互支撑？例如：
- 基本面改善 + 技术面突破 = 强信号
- 基本面恶化 + 技术面走强 = 需警惕背离

### 5. 综合结论（Synthesis）
基于以上分析，给出你的综合判断：
- **核心结论**：一段话总结（50-100字）
- **投资建议**：明确的操作建议（买入/持有/观望/减仓），并说明理由
- **风险提示**：主要风险点和不确定性
- **关键观察指标**：后续需要跟踪的关键变量

**重要**：你的综合分析应该比任何单一研究员的观点更全面、更可靠、更有洞察力。"""


class Manager:
    def __init__(self, config: AgentsConfig):
        self.config = config
        self.memory = ManagerMemory(_MEMORY_DIR)
        self.client = create_client(
            model=config.manager.model,
            system_prompt=config.manager.system_prompt,
            enable_thinking=False,  # Manager 不需要思考模型，保持 JSON 输出稳定
        )

    async def _dispatch(self, question: str) -> tuple[str, Task | str | dict]:
        """分析用户意图，决定派发策略。返回 (action, Task或直接回复或compile计划)"""
        researchers_desc = "\n".join(
            f"- id: {r.id}, 名称: {r.name}, 擅长: {r.expertise}"
            for r in self.config.researchers
        )
        wiki_context = _find_wiki_context(question) or "（暂无相关内容）"
        memory_context = self.memory.get_memory_context(question)
        prompt = DISPATCH_PROMPT_TEMPLATE.format(
            researchers_desc=researchers_desc,
            question=question,
            wiki_context=wiki_context,
            memory_context=memory_context,
        )
        text, _ = await self.client.chat(
            prompt=prompt,
            response_mime_type="application/json",
            temperature=0.3,
        )
        plan = extract_json(text)
        if plan is None:
            logger.warning("Manager dispatch JSON 解析失败，使用全部研究员: %s", text[:200])
            plan = {
                "action": "research",
                "researcher_ids": self.config.list_researcher_ids(),
                "mode": "parallel",
                "instruction": "",
            }

        if plan.get("action") == "direct":
            return "direct", question

        if plan.get("action") == "compile":
            return "compile", {
                "sources": plan.get("sources", []),
                "scope": plan.get("scope", "all"),
            }

        # 验证 researcher_ids
        valid_ids = set(self.config.list_researcher_ids())
        researcher_ids = [rid for rid in plan.get("researcher_ids", []) if rid in valid_ids]
        if not researcher_ids:
            researcher_ids = list(valid_ids)

        context = wiki_context if wiki_context != "（暂无相关内容）" else ""

        return "research", Task(
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
        parts = []
        for r in results:
            section = f"### {r.researcher_name}（{r.model}）\n{r.content}"
            if r.verification and r.verification.issues:
                warnings = [i for i in r.verification.issues if i.severity in ("error", "warning")]
                if warnings:
                    section += "\n\n**⚠ 数据验证提示：**\n" + "\n".join(f"- {i.message}" for i in warnings)
            parts.append(section)
        results_text = "\n\n".join(parts)
        prompt = SYNTHESIS_PROMPT_TEMPLATE.format(
            question=question,
            results=results_text,
        )
        text, _ = await self.client.chat(prompt=prompt, temperature=0.5)
        return text

    # ── Tool-Use Loop ─────────────────────────────────────

    _TOOL_USE_PROMPT = """你是 Lucas，A股股市知识库的首席分析师。请回答用户的问题。

## 用户问题
{question}

## 记忆
{memory_context}

## 知识库已有内容
{wiki_context}

## 可用工具
你可以调用以下工具来获取信息：
{tools_desc}

**重要：当你对问题涉及的公司、行业或概念不够确定时，先用 recall 或 search_files 查一查再回答，不要凭猜测回答。**

## 已调用的工具结果
{tool_results}

请返回 JSON：

如果你需要调用工具来获取更多信息，返回：
{{
  "action": "tool",
  "tool": "工具名",
  "args": {{"参数名": "参数值"}}
}}

如果你已有足够信息可以回答用户，返回：
{{
  "action": "answer",
  "reply": "你的回答（支持 Markdown 格式）"
}}

规则：
- 涉及文件位置、文件内容、目录结构等问题时，必须用工具查实际文件系统，不要猜测
- 闲聊、问候等简单问题直接回答，不需要调用工具
- 基于记忆和知识库能确定的信息可以直接回答
- 每次只调用一个工具
- 回答要基于事实，不要编造文件路径或内容"""

    async def _tool_use_loop(self, question: str, on_status=None, max_rounds: int = 5) -> str:
        """让 Lucas 自主决定是否调用工具，循环直到给出最终回答"""
        def status(msg):
            if on_status:
                on_status(msg)

        wiki_context = _find_wiki_context(question) or "（暂无相关内容）"
        memory_context = self.memory.get_memory_context(question)
        tools_desc = get_tools_description()

        # 自动预查：每次都先从记忆和文件中检索相关信息
        status("🔍 检索相关记忆和文档...")
        pre_results = []
        recall_output = execute_tool("recall", {"keyword": question})
        if "未找到" not in recall_output:
            pre_results.append(f"### 历史分析记录\n{recall_output}")
        search_output = execute_tool("search_files", {"keyword": question, "scope": "all"})
        if "未找到" not in search_output:
            pre_results.append(f"### 相关文件\n{search_output}")

        if pre_results:
            tool_results = "\n\n".join(pre_results)
        else:
            tool_results = "（预查无相关结果）"

        for round_num in range(max_rounds):
            prompt = self._TOOL_USE_PROMPT.format(
                question=question,
                memory_context=memory_context,
                wiki_context=wiki_context,
                tools_desc=tools_desc,
                tool_results=tool_results,
            )
            text, _ = await self.client.chat(
                prompt=prompt,
                response_mime_type="application/json",
                temperature=0.3,
            )
            result = extract_json(text)
            if result is None:
                return text

            if result.get("action") == "answer":
                return result.get("reply", "")

            if result.get("action") == "tool":
                tool_name = result.get("tool", "")
                tool_args = result.get("args", {})
                status(f"🔧 调用 {tool_name}({', '.join(f'{k}={v}' for k, v in tool_args.items())})")
                tool_output = execute_tool(tool_name, tool_args)
                if tool_results == "（预查无相关结果）":
                    tool_results = ""
                tool_results += f"\n### 工具调用 {round_num + 1}: {tool_name}\n参数: {json.dumps(tool_args, ensure_ascii=False)}\n结果:\n{tool_output}\n"
                continue

            return result.get("reply", text)

        return "抱歉，经过多轮尝试仍未能完成回答。请尝试换个方式提问。"

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
        action, dispatch_result = await self._dispatch(question)

        if action == "direct":
            status("正在思考...")
            reply = await self._tool_use_loop(question, on_status=on_status)
            self.memory.add_turn(question, "direct", reply)
            return ManagerReport(
                question=question,
                synthesis=reply,
            )

        if action == "compile":
            status("开始编译原始资料到 wiki...")
            summary = await self._compile_from_raw(dispatch_result, on_status=on_status)
            self.memory.add_turn(question, "compile", summary)
            return ManagerReport(
                question=question,
                synthesis=summary,
            )

        task = dispatch_result
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

        # 2.5 验证
        status("正在验证研究结果...")
        await asyncio.gather(*(verify_result(r) for r in results))
        for r in results:
            if r.verification and not r.verification.passed:
                status(f"⚠ {r.researcher_name}: {r.verification.error_count} 个数据问题, 置信度={r.confidence}")
            else:
                status(f"✓ {r.researcher_name} 验证通过")

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

        # 5. 整理 wiki
        status("正在整理 wiki 知识库...")
        await self._update_wiki(report, on_status=on_status)

        # 6. 更新记忆
        self.memory.add_turn(question, "research", synthesis)
        status("正在提取分析结论...")
        await self._extract_and_save_conclusion(report)
        await self._extract_and_save_preferences(question, synthesis)

        return report

    async def analyze_stream(self, question: str) -> AsyncGenerator[dict, None]:
        """
        流式分析流程，yield SSE event dicts。

        事件类型：
          status          — {"message": str}
          dispatch        — {"researchers": [{"id", "name"}], "mode": str}
          researcher_start — {"id": str, "name": str}
          researcher_chunk — {"id": str, "text": str}
          researcher_done  — {"id": str}
          synthesis_chunk  — {"text": str}
          done             — {"total_tokens": int}
        """
        def _evt(event: str, data: dict) -> dict:
            return {"event": event, "data": data}

        yield _evt("status", {"message": "正在分析问题..."})
        action, dispatch_result = await self._dispatch(question)

        # ── direct ──────────────────────────────────────────
        if action == "direct":
            yield _evt("status", {"message": "正在思考..."})
            reply = await self._tool_use_loop(question)
            self.memory.add_turn(question, "direct", reply)
            yield _evt("synthesis_chunk", {"text": reply})
            yield _evt("done", {"total_tokens": 0})
            return

        # ── compile ─────────────────────────────────────────
        if action == "compile":
            yield _evt("status", {"message": "开始编译原始资料到 wiki..."})
            summary = await self._compile_from_raw(dispatch_result)
            self.memory.add_turn(question, "compile", summary)
            yield _evt("synthesis_chunk", {"text": summary})
            yield _evt("done", {"total_tokens": 0})
            return

        # ── research ─────────────────────────────────────────
        task: Task = dispatch_result
        researcher_configs = [
            rc for rid in task.researcher_ids
            if (rc := self.config.get_researcher(rid)) is not None
        ]

        yield _evt("dispatch", {
            "researchers": [{"id": rc.id, "name": rc.name} for rc in researcher_configs],
            "mode": task.mode,
        })

        # 用 asyncio.Queue 合并并行流式事件
        results: list[ResearchResult] = []

        async def _stream_one(rc, prior: list[ResearchResult] | None = None) -> ResearchResult:
            """流式跑单个研究员，把事件放入 queue，返回结果"""
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
                content="".join(full_text) or f"[分析失败]",
                token_usage=None,
            )
            await queue.put({"event": "_researcher_result", "data": {"id": rc.id, "result": result}})
            await queue.put({"event": "researcher_done", "data": {"id": rc.id}})
            return result

        queue: asyncio.Queue = asyncio.Queue()

        if task.mode == "serial":
            async def _run_serial_stream():
                serial_prior: list[ResearchResult] = []
                for rc in researcher_configs:
                    await queue.put({"event": "researcher_start", "data": {"id": rc.id, "name": rc.name}})
                    result = await _stream_one(rc, prior=serial_prior if serial_prior else None)
                    serial_prior.append(result)
                await queue.put({"event": "_all_done", "data": {}})

            task_obj = asyncio.create_task(_run_serial_stream())
        else:
            # 并行：同时启动所有研究员
            async def _run_parallel_stream():
                for rc in researcher_configs:
                    await queue.put({"event": "researcher_start", "data": {"id": rc.id, "name": rc.name}})
                sem = asyncio.Semaphore(2)

                async def _with_sem(rc_inner):
                    async with sem:
                        await _stream_one(rc_inner)

                await asyncio.gather(*[_with_sem(rc) for rc in researcher_configs])
                await queue.put({"event": "_all_done", "data": {}})

            task_obj = asyncio.create_task(_run_parallel_stream())

        # 消费 queue，转发事件给调用方
        pending_done = len(researcher_configs)
        while True:
            evt = await queue.get()
            if evt["event"] == "_researcher_result":
                results.append(evt["data"]["result"])
                continue
            if evt["event"] == "_all_done":
                break
            yield evt

        await task_obj  # 确保任务完成，传播异常

        # 汇总
        yield _evt("status", {"message": "正在汇总分析结果..."})
        if len(results) > 1:
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

        yield _evt("synthesis_chunk", {"text": synthesis})

        # 归档 + wiki + 记忆
        yield _evt("status", {"message": "正在归档分析结果..."})
        self._archive(report)
        yield _evt("status", {"message": "正在整理 wiki 知识库..."})
        await self._update_wiki(report)
        self.memory.add_turn(question, "research", synthesis)
        await self._extract_and_save_conclusion(report)
        await self._extract_and_save_preferences(question, synthesis)

        yield _evt("done", {"total_tokens": total_tokens})

    _CONCLUSION_EXTRACT_PROMPT = """从分析报告中提取结论摘要。

## 报告
{synthesis}

返回 JSON：
{{
  "topics": ["涉及的股票代码或关键主题，如 300750、宁德时代、新能源"],
  "conclusion": "一句话核心结论（50字以内）",
  "sentiment": "bullish 或 bearish 或 neutral"
}}"""

    _PREFERENCE_EXTRACT_PROMPT = """从本次对话中提取用户偏好变化。

## 用户问题
{question}

## 分析摘要
{summary}

## 当前用户偏好
{current_prefs}

如果发现新的关注股票、行业、风险偏好等，返回更新后的完整 JSON：
{{
  "watchlist": ["股票代码列表"],
  "focus_industries": ["行业列表"],
  "risk_preference": "conservative 或 moderate 或 aggressive",
  "analysis_style": "简洁 或 详细",
  "custom_notes": ["用户特殊偏好备注"]
}}

如果没有明显变化，返回 null。"""

    async def _extract_and_save_conclusion(self, report: ManagerReport):
        try:
            prompt = self._CONCLUSION_EXTRACT_PROMPT.format(
                synthesis=report.synthesis[:1000],
            )
            text, _ = await self.client.chat(
                prompt=prompt,
                response_mime_type="application/json",
                temperature=0.1,
            )
            data = extract_json(text)
            if data is None:
                return
            self.memory.add_conclusion(
                question=report.question,
                topics=data.get("topics", []),
                conclusion=data.get("conclusion", ""),
                sentiment=data.get("sentiment", "neutral"),
                researchers=[r.researcher_id for r in report.results],
            )
        except Exception as e:
            logger.warning("提取分析结论失败: %s", e)

    async def _extract_and_save_preferences(self, question: str, synthesis: str):
        try:
            current = self.memory.load_preferences()
            prompt = self._PREFERENCE_EXTRACT_PROMPT.format(
                question=question,
                summary=synthesis[:500],
                current_prefs=json.dumps(current, ensure_ascii=False) if current else "（暂无）",
            )
            text, _ = await self.client.chat(
                prompt=prompt,
                response_mime_type="application/json",
                temperature=0.1,
            )
            data = extract_json(text)
            if data:
                self.memory.save_preferences(data)
        except Exception as e:
            logger.warning("提取用户偏好失败: %s", e)

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

            # 兜底：如果正文中缺少参考资料章节，从 source_urls 补全
            body = r.content
            if r.source_urls and "## 参考资料" not in body:
                urls_section = "\n\n## 参考资料\n" + "\n".join(
                    f"- [{u['title']}]({u['url']})" for u in r.source_urls
                )
                body += urls_section

            if r.verification and r.verification.issues:
                body += r.verification.to_markdown()

            content = (
                f"---\n"
                f"question: {report.question}\n"
                f"researcher: {r.researcher_name}\n"
                f"model: {r.model}\n"
                f"date: {today}\n"
                f"confidence: {r.confidence}\n"
                f"---\n\n"
                f"{body}\n"
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

        # 汇总所有研究员的参考链接
        all_urls = []
        seen_urls = set()
        for r in report.results:
            for u in r.source_urls:
                if u["url"] not in seen_urls:
                    seen_urls.add(u["url"])
                    all_urls.append(u)
        ref_section = ""
        if all_urls:
            ref_section = (
                "\n\n## 参考资料\n"
                + "\n".join(f"- [{u['title']}]({u['url']})" for u in all_urls)
                + "\n"
            )

        # 动态置信度：取所有研究员中最低的
        confidences = [r.confidence for r in report.results]
        if "low" in confidences:
            overall_confidence = "low"
        elif all(c == "high" for c in confidences):
            overall_confidence = "high"
        else:
            overall_confidence = "medium"

        # 验证汇总
        verify_section = ""
        all_issues = []
        for r in report.results:
            if r.verification:
                for issue in r.verification.issues:
                    all_issues.append(f"- [{r.researcher_name}] {issue.message}")
        if all_issues:
            verify_section = "\n\n## 数据验证汇总\n" + "\n".join(all_issues) + "\n"

        wiki_content = (
            f"---\n"
            f"title: {report.question}\n"
            f"type: report\n"
            f"created: {today}\n"
            f"updated: {today}\n"
            f"sources:\n{sources}\n"
            f"researchers: {researchers_list}\n"
            f"tags: [分析报告]\n"
            f"confidence: {overall_confidence}\n"
            f"---\n\n"
            f"{report.synthesis}{ref_section}{verify_section}\n"
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

    # ── Wiki 整理 ──────────────────────────────────────────

    _WIKI_PLAN_PROMPT = """你是 Wiki 编辑，需要判断本次分析报告应该更新哪些 wiki 页面。

## 分析报告
{synthesis}

## 现有 wiki 页面
{existing_pages}

## 可用页面类型
- company: wiki/companies/{{代码}}-{{简称}}.md（公司档案）
- industry: wiki/industries/{{行业名}}.md（行业概览）
- concept: wiki/concepts/{{概念名}}.md（概念/主题）

请返回 JSON 数组，每个元素：
{{
  "type": "company|industry|concept",
  "name": "页面名称（如 300750-宁德时代）",
  "action": "create|update",
  "reason": "为什么需要更新/创建"
}}

规则：
- 只列出本次分析确实涉及且有新信息可补充的页面
- 如果分析内容太泛、没有具体可落地的信息，返回空数组 []
- 不要创建信息量不足的页面"""

    _WIKI_COMPILE_PROMPT = """你是 Wiki 编辑，需要根据分析报告更新一个 wiki 页面。

## 编译模板
{template}

## 当前页面内容
{current_content}

## 本次分析报告
{synthesis}

## 任务
{task_desc}

请输出完整的更新后页面内容（包含 frontmatter）。

规则：
- 增量更新：保留已有内容，补充新信息
- 新增信息用（{today}更新）标注
- 如果新旧信息矛盾，保留两者并标注时间
- 更新 frontmatter 的 updated 日期为 {today}
- 在 sources 中追加本次分析来源
- 严格遵循编译模板的格式"""

    def _list_wiki_pages(self) -> str:
        pages = []
        for md_path in glob.glob(os.path.join(_WIKI_DIR, "**", "*.md"), recursive=True):
            rel = os.path.relpath(md_path, _WIKI_DIR)
            if rel in ("index.md", "glossary.md") or rel.startswith("reports/"):
                continue
            pages.append(f"- {rel}")
        return "\n".join(pages) if pages else "（暂无）"

    def _load_template(self, page_type: str) -> str:
        type_to_template = {
            "company": "compile-company.md",
            "industry": "compile-industry.md",
            "concept": "compile-concept.md",
        }
        template_file = type_to_template.get(page_type)
        if not template_file:
            return ""
        path = os.path.join(_PROMPTS_DIR, template_file)
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return ""

    def _page_path(self, page_type: str, name: str) -> str:
        type_to_dir = {
            "company": "companies",
            "industry": "industries",
            "concept": "concepts",
        }
        subdir = type_to_dir.get(page_type, page_type)
        return os.path.join(_WIKI_DIR, subdir, f"{name}.md")

    async def _plan_wiki_updates(self, report: ManagerReport) -> list[dict]:
        prompt = self._WIKI_PLAN_PROMPT.format(
            synthesis=report.synthesis,
            existing_pages=self._list_wiki_pages(),
        )
        text, _ = await self.client.chat(
            prompt=prompt,
            response_mime_type="application/json",
            temperature=0.3,
        )
        plans = extract_json(text)
        if plans is None or not isinstance(plans, list):
            logger.warning("Wiki 更新计划 JSON 解析失败: %s", text[:200])
            return []
        return plans

    async def _compile_wiki_page(self, page_plan: dict, report: ManagerReport) -> str:
        page_type = page_plan["type"]
        name = page_plan["name"]
        action = page_plan.get("action", "update")

        template = self._load_template(page_type)
        page_path = self._page_path(page_type, name)

        current_content = ""
        if action == "update":
            try:
                with open(page_path, "r", encoding="utf-8") as f:
                    current_content = f.read()
            except FileNotFoundError:
                action = "create"

        if action == "create":
            task_desc = f"创建新的 {page_type} 页面：{name}"
            current_content = "（新页面，尚无内容）"
        else:
            task_desc = f"增量更新 {page_type} 页面：{name}。原因：{page_plan.get('reason', '')}"

        today = date.today().isoformat()
        prompt = self._WIKI_COMPILE_PROMPT.format(
            template=template,
            current_content=current_content,
            synthesis=report.synthesis,
            task_desc=task_desc,
            today=today,
        )
        text, _ = await self.client.chat(prompt=prompt, temperature=0.3)
        return text

    async def _update_wiki(self, report: ManagerReport, on_status=None):
        def status(msg):
            if on_status:
                on_status(msg)

        plans = await self._plan_wiki_updates(report)
        if not plans:
            status("本次分析无需更新 wiki 页面")
            return

        status(f"需要更新 {len(plans)} 个 wiki 页面")

        for plan in plans:
            page_type = plan.get("type", "")
            name = plan.get("name", "")
            action = plan.get("action", "update")
            if not page_type or not name:
                continue

            status(f"  {'创建' if action == 'create' else '更新'} {page_type}/{name}...")
            try:
                new_content = await self._compile_wiki_page(plan, report)
                page_path = self._page_path(page_type, name)
                os.makedirs(os.path.dirname(page_path), exist_ok=True)
                with open(page_path, "w", encoding="utf-8") as f:
                    f.write(new_content)

                # 更新 index
                type_to_section = {
                    "company": "## 公司档案",
                    "industry": "## 行业概览",
                    "concept": "## 概念/主题",
                }
                section = type_to_section.get(page_type)
                if section:
                    type_to_dir = {"company": "companies", "industry": "industries", "concept": "concepts"}
                    rel_path = f"{type_to_dir[page_type]}/{name}.md"
                    self._update_wiki_index(section, rel_path, name)

                status(f"  ✓ {page_type}/{name}")
            except Exception as e:
                logger.warning("更新 wiki 页面失败 %s/%s: %s", page_type, name, e)
                status(f"  ✗ {page_type}/{name}: {e}")

    def _update_wiki_index(self, section_header: str, rel_path: str, display_name: str):
        index_path = os.path.join(_WIKI_DIR, "index.md")
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                content = f.read()
        except FileNotFoundError:
            return

        if rel_path in content:
            return

        entry = f"- [{display_name}]({rel_path})"
        placeholder = "（暂无，等待编译）"

        if section_header in content:
            section_content = content.split(section_header, 1)[1]
            if placeholder in section_content.split("\n##")[0]:
                content = content.replace(
                    f"{section_header}\n{placeholder}",
                    f"{section_header}\n{entry}",
                )
            else:
                content = content.replace(section_header, f"{section_header}\n{entry}", 1)

        with open(index_path, "w", encoding="utf-8") as f:
            f.write(content)

    # ── 从 raw/ 编译 wiki ─────────────────────────────────────

    _RAW_CLASSIFY_PROMPT = """你是 Wiki 编辑。根据以下原始资料的内容，判断应该编译成什么类型的 wiki 页面。

## 原始资料路径
{raw_path}

## 原始资料内容
{raw_content}

## 现有 wiki 页面
{existing_pages}

请返回 JSON 数组，每个元素代表一个应创建或更新的 wiki 页面：
{{
  "type": "company|industry|concept",
  "name": "页面名称（如 300750-宁德时代）",
  "action": "create|update",
  "reason": "为什么需要创建/更新"
}}

规则：
- 一份资料可能涉及多个页面（如一份研报同时涉及公司和行业）
- 公司页面用 "股票代码-简称" 命名（如 300750-宁德时代）
- 如果现有页面中已有相关页面，action 设为 update
- 如果资料信息量不足以支撑一个页面，返回空数组 []"""

    _RAW_COMPILE_PROMPT = """你是 Wiki 编辑，需要根据原始资料编译一个 wiki 页面。

## 编译模板
{template}

## 当前页面内容
{current_content}

## 原始资料
{raw_content}

## 任务
{task_desc}

请输出完整的页面内容（包含 frontmatter）。

规则：
- 增量更新：保留已有内容，补充新信息
- 新增信息用（{today}更新）标注
- 如果新旧信息矛盾，保留两者并标注时间
- 更新 frontmatter 的 updated 日期为 {today}
- 在 sources 中包含原始资料路径：{raw_path}
- 严格遵循编译模板的格式
- 区分事实和观点，观点标注来源"""

    def _find_compiled_sources(self) -> set[str]:
        """扫描 wiki/ 页面的 frontmatter，收集已编译过的 raw/ 路径"""
        compiled = set()
        for md_path in glob.glob(os.path.join(_WIKI_DIR, "**", "*.md"), recursive=True):
            try:
                with open(md_path, "r", encoding="utf-8") as f:
                    content = f.read()
                if not content.startswith("---"):
                    continue
                end = content.index("---", 3)
                frontmatter = content[3:end]
                for line in frontmatter.split("\n"):
                    line = line.strip().lstrip("- ")
                    if line.startswith("raw/"):
                        compiled.add(line)
            except (ValueError, FileNotFoundError):
                continue
        return compiled

    def _find_raw_files(self, compile_plan: dict) -> list[str]:
        """根据 compile 计划确定要编译的文件列表"""
        raw_dir = os.path.join(_PROJECT_ROOT, "raw")

        if compile_plan.get("scope") == "specific" and compile_plan.get("sources"):
            paths = []
            for src in compile_plan["sources"]:
                full = os.path.join(_PROJECT_ROOT, src)
                if os.path.isfile(full):
                    paths.append(full)
            return paths

        # scope == "all": 扫描 raw/ 下所有 .md，排除 reports/ 子目录和已编译的
        compiled = self._find_compiled_sources()
        paths = []
        for md_path in sorted(glob.glob(os.path.join(raw_dir, "**", "*.md"), recursive=True)):
            rel = os.path.relpath(md_path, _PROJECT_ROOT)
            if rel.startswith("raw/reports/"):
                continue
            if rel in compiled:
                continue
            paths.append(md_path)
        return paths

    async def _compile_from_raw(self, compile_plan: dict, on_status=None) -> str:
        """从 raw/ 原始资料编译 wiki 页面"""
        def status(msg):
            if on_status:
                on_status(msg)

        raw_files = self._find_raw_files(compile_plan)
        if not raw_files:
            status("没有找到需要编译的原始资料")
            return "没有找到需要编译的原始资料。所有 raw/ 文件可能已经编译过了。"

        status(f"找到 {len(raw_files)} 个待编译文件")
        compiled_pages = []

        for raw_path in raw_files:
            rel_path = os.path.relpath(raw_path, _PROJECT_ROOT)
            status(f"正在处理: {rel_path}")

            try:
                with open(raw_path, "r", encoding="utf-8") as f:
                    raw_content = f.read()
            except FileNotFoundError:
                status(f"  ✗ 文件不存在: {rel_path}")
                continue

            # 1. 分类：判断应该生成哪些 wiki 页面
            classify_prompt = self._RAW_CLASSIFY_PROMPT.format(
                raw_path=rel_path,
                raw_content=raw_content[:8000],
                existing_pages=self._list_wiki_pages(),
            )
            text, _ = await self.client.chat(
                prompt=classify_prompt,
                response_mime_type="application/json",
                temperature=0.3,
            )
            plans = extract_json(text)
            if plans is None or not isinstance(plans, list):
                logger.warning("编译分类 JSON 解析失败: %s", rel_path)
                plans = []

            if not plans:
                status(f"  跳过（信息量不足）: {rel_path}")
                continue

            # 2. 逐个编译 wiki 页面
            for plan in plans:
                page_type = plan.get("type", "")
                name = plan.get("name", "")
                action = plan.get("action", "create")
                if not page_type or not name:
                    continue

                template = self._load_template(page_type)
                page_path = self._page_path(page_type, name)

                current_content = ""
                if action == "update":
                    try:
                        with open(page_path, "r", encoding="utf-8") as f:
                            current_content = f.read()
                    except FileNotFoundError:
                        action = "create"

                if action == "create":
                    task_desc = f"根据原始资料创建新的 {page_type} 页面：{name}"
                    current_content = "（新页面，尚无内容）"
                else:
                    task_desc = f"根据原始资料增量更新 {page_type} 页面：{name}。原因：{plan.get('reason', '')}"

                today = date.today().isoformat()
                compile_prompt = self._RAW_COMPILE_PROMPT.format(
                    template=template,
                    current_content=current_content,
                    raw_content=raw_content[:8000],
                    task_desc=task_desc,
                    today=today,
                    raw_path=rel_path,
                )

                status(f"  {'创建' if action == 'create' else '更新'} {page_type}/{name}...")
                try:
                    new_content, _ = await self.client.chat(prompt=compile_prompt, temperature=0.3)
                    os.makedirs(os.path.dirname(page_path), exist_ok=True)
                    with open(page_path, "w", encoding="utf-8") as f:
                        f.write(new_content)

                    type_to_section = {
                        "company": "## 公司档案",
                        "industry": "## 行业概览",
                        "concept": "## 概念/主题",
                    }
                    section = type_to_section.get(page_type)
                    if section:
                        type_to_dir = {"company": "companies", "industry": "industries", "concept": "concepts"}
                        wiki_rel = f"{type_to_dir[page_type]}/{name}.md"
                        self._update_wiki_index(section, wiki_rel, name)

                    compiled_pages.append(f"{action}: {page_type}/{name}")
                    status(f"  ✓ {page_type}/{name}")
                except Exception as e:
                    logger.warning("编译 wiki 页面失败 %s/%s: %s", page_type, name, e)
                    status(f"  ✗ {page_type}/{name}: {e}")

        if compiled_pages:
            summary = f"编译完成，共处理 {len(raw_files)} 个文件，生成/更新 {len(compiled_pages)} 个 wiki 页面：\n" + "\n".join(f"- {p}" for p in compiled_pages)
        else:
            summary = f"处理了 {len(raw_files)} 个文件，但没有生成新的 wiki 页面（可能信息量不足）。"
        return summary
