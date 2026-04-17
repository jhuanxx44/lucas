import asyncio
import glob
import json
import logging
import os
from datetime import date
from typing import Optional

from agents.config import AgentsConfig
from agents.models import Task, ResearchResult, ManagerReport
from agents.memory import ManagerMemory
from agents.researcher import run_researcher, _find_wiki_context
from utils.llm_client import create_client

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

请返回 JSON。首先判断用户意图：

1. 如果是闲聊、问候、闲谈等非分析类问题，返回：
{{
  "action": "chat",
  "reply": "你的直接回复"
}}

2. 如果知识库已有内容足以回答用户问题，直接基于知识库内容回答，返回：
{{
  "action": "wiki",
  "reply": "基于知识库内容的回答"
}}

3. 如果需要研究员进行新的研究分析（知识库没有相关内容，或用户明确要求最新数据/深度分析），返回：
{{
  "action": "research",
  "researcher_ids": ["要派发的研究员id列表"],
  "mode": "parallel 或 serial",
  "instruction": "给研究员的统一指令（补充说明、分析重点等）"
}}

4. 如果用户要求编译 raw/ 中的原始资料到 wiki（如"编译 raw/xxx.md"、"处理这份研报"、"整理原始资料"、"更新知识库"），返回：
{{
  "action": "compile",
  "sources": ["raw/路径/文件.md"],
  "scope": "all 或 specific"
}}

规则：
- 问候、闲聊、简单对话直接用 chat 回复，不要派发研究员
- 知识库已有足够信息时，优先用 wiki 直接回答，节省研究员资源
- 只有知识库信息不足或用户需要最新实时数据时，才派发研究员
- "编译"、"整理 wiki"、"处理研报"、"更新知识库"、"编译所有原始资料" 等指令用 compile
- 如果用户指定了具体文件路径，放入 sources 并设 scope 为 specific
- 如果用户说"编译所有"或没指定文件，scope 设为 all，sources 为空数组
- 结合对话历史理解用户意图（如"继续分析"指的是上一轮的主题）
- 结合用户画像了解用户偏好（关注的股票、行业等）
- 参考历史分析结论，避免重复分析，或对比前后变化
- 根据问题性质选择合适的研究员，不必每次都全选
- 如果问题需要多角度交叉验证，选多个研究员
- 如果后续研究员需要参考前序结果（如先基本面再技术面），用 serial
- 简单问题可以只派一个研究员"""

SYNTHESIS_PROMPT_TEMPLATE = """你是 Lucas，需要汇总各研究员的分析结果。

## 用户原始问题
{question}

## 各研究员分析
{results}

请给出综合分析报告，包含：
1. **综合结论** — 一段话总结
2. **各方观点** — 简要列出每位研究员的核心观点
3. **一致之处** — 研究员们达成共识的部分
4. **分歧之处** — 研究员们意见不同的部分（如有）
5. **综合建议** — 你作为 Lucas 的最终建议"""


class Manager:
    def __init__(self, config: AgentsConfig):
        self.config = config
        self.memory = ManagerMemory(_MEMORY_DIR)
        self.client = create_client(
            model=config.manager.model,
            system_prompt=config.manager.system_prompt,
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
        try:
            plan = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Manager dispatch JSON 解析失败，使用全部研究员")
            plan = {
                "action": "research",
                "researcher_ids": self.config.list_researcher_ids(),
                "mode": "parallel",
                "instruction": "",
            }

        if plan.get("action") in ("chat", "wiki"):
            return plan["action"], plan.get("reply", "你好！有什么A股相关的问题我可以帮你分析？")

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
        action, dispatch_result = await self._dispatch(question)

        if action == "chat":
            self.memory.add_turn(question, "chat", dispatch_result)
            return ManagerReport(
                question=question,
                synthesis=dispatch_result,
            )

        if action == "wiki":
            status("知识库已有相关内容，直接回答")
            self.memory.add_turn(question, "wiki", dispatch_result)
            return ManagerReport(
                question=question,
                synthesis=dispatch_result,
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
            data = json.loads(text)
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
            data = json.loads(text)
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
        try:
            plans = json.loads(text)
            if not isinstance(plans, list):
                return []
            return plans
        except json.JSONDecodeError:
            logger.warning("Wiki 更新计划 JSON 解析失败")
            return []

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
            try:
                plans = json.loads(text)
                if not isinstance(plans, list):
                    plans = []
            except json.JSONDecodeError:
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
