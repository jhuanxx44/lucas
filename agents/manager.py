import asyncio
import json
import logging
import os
from typing import AsyncGenerator

from agents.config import AgentsConfig
from agents.models import Task, ResearcherTask, ResearchResult, ManagerReport
from agents.memory import ManagerMemory
from agents.researcher import _find_wiki_context
from agents.research_service import ResearchService
from agents.knowledge_service import KnowledgeService
from agents.tools import get_tools_description, execute_tool
from utils.llm_client import create_client
from utils.json_extract import extract_json

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
_PROMPTS_DIR = os.path.join(_PROJECT_ROOT, "prompts")
_MEMORY_DIR = os.path.join(_PROJECT_ROOT, "memory")


class Manager:
    def __init__(self, config: AgentsConfig):
        self.config = config
        self.memory = ManagerMemory(_MEMORY_DIR)
        self.client = create_client(
            model=config.manager.model,
            system_prompt=config.manager.system_prompt,
            enable_thinking=False,
        )
        self.research_service = ResearchService(config, self.client, self._load_prompt)
        self.knowledge_service = KnowledgeService(self.client, self.memory, self._load_prompt)

    def _load_prompt(self, name: str) -> str:
        path = os.path.join(_PROMPTS_DIR, f"{name}.md")
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        if content.startswith("---\n"):
            end = content.find("\n---\n", 4)
            if end != -1:
                content = content[end + 5:]
        return content

    async def _dispatch(self, question: str) -> tuple[str, Task | str | dict]:
        """分析用户意图，决定派发策略。返回 (action, Task或直接回复或compile计划)"""
        researchers_desc = "\n".join(
            f"- id: {r.id}, 名称: {r.name}, 擅长: {r.expertise}"
            for r in self.config.researchers
        )
        wiki_context = _find_wiki_context(question) or "（暂无相关内容）"
        memory_context = self.memory.get_memory_context(question)
        prompt = self._load_prompt("dispatch").format(
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

        valid_ids = set(self.config.list_researcher_ids())
        researcher_ids = [rid for rid in plan.get("researcher_ids", []) if rid in valid_ids]
        if not researcher_ids:
            researcher_ids = list(valid_ids)

        context = wiki_context if wiki_context != "（暂无相关内容）" else ""

        researcher_tasks = {}
        raw_tasks = plan.get("tasks", {})
        for rid in researcher_ids:
            rt = raw_tasks.get(rid, {})
            researcher_tasks[rid] = ResearcherTask(
                sub_question=rt.get("sub_question", ""),
                focus=rt.get("focus", ""),
                avoid=rt.get("avoid", ""),
            )

        return "research", Task(
            question=question,
            instruction=plan.get("instruction", ""),
            researcher_ids=researcher_ids,
            mode=plan.get("mode", "parallel"),
            context=context,
            researcher_tasks=researcher_tasks,
        )

    async def _tool_use_loop(self, question: str, on_status=None, max_rounds: int = 5) -> str:
        """让 Lucas 自主决定是否调用工具，循环直到给出最终回答"""
        def status(msg):
            if on_status:
                on_status(msg)

        wiki_context = _find_wiki_context(question) or "（暂无相关内容）"
        memory_context = self.memory.get_memory_context(question)
        tools_desc = get_tools_description()

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
            prompt = self._load_prompt("tool-use").format(
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
            summary = await self.knowledge_service.compile_from_raw(dispatch_result, on_status=on_status)
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

        results = await self.research_service.run(task, on_status=on_status)

        if len(results) > 1:
            status("正在汇总分析结果...")
            synthesis = await self.research_service.synthesize(question, results)
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

        await self.knowledge_service.persist_report(report, on_status=on_status)
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

        if action == "direct":
            yield _evt("status", {"message": "正在思考..."})
            reply = await self._tool_use_loop(question)
            self.memory.add_turn(question, "direct", reply)
            yield _evt("synthesis_chunk", {"text": reply})
            yield _evt("done", {"total_tokens": 0})
            return

        if action == "compile":
            yield _evt("status", {"message": "开始编译原始资料到 wiki..."})
            summary = await self.knowledge_service.compile_from_raw(dispatch_result)
            self.memory.add_turn(question, "compile", summary)
            yield _evt("synthesis_chunk", {"text": summary})
            yield _evt("done", {"total_tokens": 0})
            return

        task: Task = dispatch_result
        researcher_configs = [
            rc for rid in task.researcher_ids
            if (rc := self.config.get_researcher(rid)) is not None
        ]

        yield _evt("dispatch", {
            "researchers": [{"id": rc.id, "name": rc.name} for rc in researcher_configs],
            "mode": task.mode,
        })

        results: list[ResearchResult] = []
        async for evt in self.research_service.run_stream(task):
            if evt["event"] == "_results":
                results = evt["data"]["results"]
                continue
            yield evt

        yield _evt("status", {"message": "正在汇总分析结果..."})
        if len(results) > 1:
            synthesis = await self.research_service.synthesize(question, results)
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

        def _emit_status(msg):
            self._pending_status.append(msg)

        self._pending_status = []
        await self.knowledge_service.persist_report(report, on_status=_emit_status)
        for msg in self._pending_status:
            yield _evt("status", {"message": msg})
        del self._pending_status

        yield _evt("done", {"total_tokens": total_tokens})
