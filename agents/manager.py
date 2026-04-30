import asyncio
import json
import logging
import os
import time
import uuid
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


def _cleanup_download_tmp(tmp_path: str):
    stem, _ = os.path.splitext(tmp_path)
    for ext in (".md", ".pdf"):
        candidate = stem + ext
        if os.path.isfile(candidate):
            os.remove(candidate)
    tmp_parent = os.path.dirname(tmp_path)
    if os.path.isdir(tmp_parent) and not os.listdir(tmp_parent):
        os.rmdir(tmp_parent)


class Manager:
    _PENDING_PATH = os.path.join(_MEMORY_DIR, "_pending_ingest.json")
    _PENDING_DIR = os.path.join(_MEMORY_DIR, "pending_ingest")
    _PENDING_ACTION_PREFIX = "__ingest_confirm__:"
    _PENDING_TTL_SECONDS = 24 * 60 * 60

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

    def _cleanup_pending_ingest(self):
        if not os.path.isdir(self._PENDING_DIR):
            return
        cutoff = time.time() - self._PENDING_TTL_SECONDS
        for name in os.listdir(self._PENDING_DIR):
            if not name.endswith(".json"):
                continue
            path = os.path.join(self._PENDING_DIR, name)
            try:
                if os.path.getmtime(path) < cutoff:
                    os.remove(path)
            except FileNotFoundError:
                continue
            except Exception as e:
                logger.warning("清理过期 pending ingest 失败 %s: %s", path, e)

    def _pending_path(self, pending_id: str) -> str:
        safe_id = os.path.basename(pending_id)
        if safe_id != pending_id or not safe_id.endswith(".json"):
            safe_id = f"{safe_id}.json"
        return os.path.join(self._PENDING_DIR, safe_id)

    def _save_pending_ingest(self, pending: dict) -> str:
        self._cleanup_pending_ingest()
        os.makedirs(self._PENDING_DIR, exist_ok=True)
        pending_id = f"{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        pending["pending_id"] = pending_id
        with open(self._pending_path(pending_id), "w", encoding="utf-8") as f:
            json.dump(pending, f, ensure_ascii=False)
        return pending_id

    def _parse_pending_action(self, question: str) -> dict | None:
        if not question.startswith(self._PENDING_ACTION_PREFIX):
            return None
        rest = question[len(self._PENDING_ACTION_PREFIX):]
        pending_id, sep, industry = rest.partition(":")
        if not sep or not pending_id or not industry:
            return None
        return {"pending_id": pending_id, "industry": industry}

    def _load_pending_ingest(self, pending_id: str = "") -> tuple[dict | None, str]:
        self._cleanup_pending_ingest()

        if pending_id:
            path = self._pending_path(pending_id)
            if not os.path.isfile(path):
                return None, "missing"
            with open(path, "r", encoding="utf-8") as f:
                pending = json.load(f)
            os.remove(path)
            return pending, "ok"

        if os.path.isfile(self._PENDING_PATH):
            with open(self._PENDING_PATH, "r", encoding="utf-8") as f:
                pending = json.load(f)
            os.remove(self._PENDING_PATH)
            return pending, "ok"

        pending_files = []
        if os.path.isdir(self._PENDING_DIR):
            pending_files = [
                name for name in os.listdir(self._PENDING_DIR)
                if name.endswith(".json") and os.path.isfile(os.path.join(self._PENDING_DIR, name))
            ]
        if len(pending_files) == 1:
            pending_id = pending_files[0][:-5]
            return self._load_pending_ingest(pending_id)
        if len(pending_files) > 1:
            return None, "ambiguous"
        return None, "missing"

    def _pending_action_value(self, pending_id: str, industry: str) -> str:
        return f"{self._PENDING_ACTION_PREFIX}{pending_id}:{industry}"

    async def _dispatch(self, question: str) -> tuple[str, Task | str | dict]:
        pending_action = self._parse_pending_action(question)
        if pending_action:
            return "ingest_confirm", pending_action

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

        if plan.get("action") == "ingest":
            return "ingest", {
                "url": plan.get("url", ""),
                "title": plan.get("title", ""),
                "industry": plan.get("industry", ""),
                "company": plan.get("company", ""),
            }

        if plan.get("action") == "ingest_confirm":
            return "ingest_confirm", {
                "pending_id": plan.get("pending_id", ""),
                "industry": plan.get("industry", ""),
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
            industry=plan.get("industry", ""),
            companies=plan.get("companies", []),
        )

    async def _tool_use_loop(self, question: str, max_rounds: int = 5) -> str:
        wiki_context = _find_wiki_context(question) or "（暂无相关内容）"
        memory_context = self.memory.get_memory_context(question)
        tools_desc = get_tools_description()

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
                tool_output = execute_tool(tool_name, tool_args)
                if tool_results == "（预查无相关结果）":
                    tool_results = ""
                tool_results += f"\n### 工具调用 {round_num + 1}: {tool_name}\n参数: {json.dumps(tool_args, ensure_ascii=False)}\n结果:\n{tool_output}\n"
                continue

            return result.get("reply", text)

        return "抱歉，经过多轮尝试仍未能完成回答。请尝试换个方式提问。"

    async def analyze(self, question: str) -> AsyncGenerator[dict, None]:
        """
        分析流程，yield SSE event dicts。

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

        if action == "ingest":
            yield _evt("status", {"message": "正在收录外部材料..."})
            status_msgs = []

            def _on_status(msg):
                status_msgs.append(msg)

            try:
                ingest_url = dispatch_result.get("url", "")
                ingest_content = ""

                if ingest_url:
                    from utils.source_collector import download_single_url
                    tmp_dir = os.path.join(_PROJECT_ROOT, "raw", "sources", "_tmp")
                    dl_result = await download_single_url(ingest_url, tmp_dir, dispatch_result.get("title", ""))
                    if dl_result is None:
                        yield _evt("synthesis_chunk", {"text": f"无法抓取 URL: {ingest_url}"})
                        yield _evt("done", {"total_tokens": 0})
                        return
                    tmp_path = os.path.join(_PROJECT_ROOT, dl_result["path"])
                    with open(tmp_path, "r", encoding="utf-8") as f:
                        ingest_content = f.read()
                    _cleanup_download_tmp(tmp_path)

                if not ingest_content.strip():
                    yield _evt("synthesis_chunk", {"text": "抓取的内容为空，无法收录。"})
                    yield _evt("done", {"total_tokens": 0})
                    return

                yield _evt("status", {"message": "正在分类..."})
                title = dispatch_result.get("title", "")
                industry = dispatch_result.get("industry", "")
                company = dispatch_result.get("company", "")

                classification = None
                if not title or not industry:
                    classification = await self.knowledge_service.classify_source(ingest_content)
                    title = title or classification["title"]
                    industry = industry or classification["industry"]
                    company = company or classification["company"]

                if classification and classification.get("confidence") == "low" and classification.get("alternatives"):
                    pending = {
                        "content": ingest_content,
                        "url": ingest_url,
                        "title": title,
                        "industry": industry,
                        "company": company,
                        "alternatives": classification["alternatives"],
                    }
                    pending_id = self._save_pending_ingest(pending)

                    alts = classification["alternatives"]
                    alt_text = "、".join(a["industry"] for a in alts)
                    yield _evt("synthesis_chunk", {
                        "text": f"材料已抓取，但行业归属不确定。\n\n系统建议归入 **{industry}**，但也可能属于 {alt_text}。\n\n请选择归类方式：",
                    })
                    actions = [{"label": industry, "value": self._pending_action_value(pending_id, industry)}]
                    for alt in alts:
                        alt_industry = alt["industry"]
                        actions.append({
                            "label": alt_industry,
                            "value": self._pending_action_value(pending_id, alt_industry),
                        })
                    yield _evt("actions", {"actions": actions})
                    yield _evt("done", {"total_tokens": 0})
                    return

                yield _evt("status", {"message": f"分类: {industry}/{company or '行业级'} — {title}"})

                result = await self.knowledge_service.ingest_source(
                    content=ingest_content,
                    title=title,
                    industry=industry,
                    url=ingest_url,
                    company=company,
                    on_status=_on_status,
                )
                for msg in status_msgs:
                    yield _evt("status", {"message": msg})
                summary = (
                    f"已收录材料到 `{result['path']}`\n\n"
                    f"- 行业: {result['industry']}\n"
                    f"- 公司: {result['company'] or '(行业级)'}\n"
                    f"- 标题: {result['title']}\n"
                )
                if result["compiled_pages"]:
                    summary += f"\n已编译到 wiki:\n" + "\n".join(f"- {p}" for p in result["compiled_pages"])
                self.memory.add_turn(question, "ingest", summary)
                yield _evt("synthesis_chunk", {"text": summary})
            except Exception as e:
                yield _evt("synthesis_chunk", {"text": f"收录失败: {e}"})
            yield _evt("done", {"total_tokens": 0})
            return

        if action == "ingest_confirm":
            pending, pending_status = self._load_pending_ingest(dispatch_result.get("pending_id", ""))
            if pending_status == "ambiguous":
                yield _evt("synthesis_chunk", {"text": "存在多个待确认的收录任务，请点击对应材料下方的归类按钮。"})
                yield _evt("done", {"total_tokens": 0})
                return
            if pending is None:
                yield _evt("synthesis_chunk", {"text": "待确认的收录任务不存在或已过期。"})
                yield _evt("done", {"total_tokens": 0})
                return

            chosen_industry = dispatch_result.get("industry", "") or pending["industry"]
            yield _evt("status", {"message": f"确认归类到 {chosen_industry}，正在收录..."})

            status_msgs = []

            def _on_confirm_status(msg):
                status_msgs.append(msg)

            try:
                result = await self.knowledge_service.ingest_source(
                    content=pending["content"],
                    title=pending["title"],
                    industry=chosen_industry,
                    url=pending.get("url", ""),
                    company=pending.get("company", ""),
                    on_status=_on_confirm_status,
                )
                for msg in status_msgs:
                    yield _evt("status", {"message": msg})
                summary = (
                    f"已收录材料到 `{result['path']}`\n\n"
                    f"- 行业: {result['industry']}\n"
                    f"- 公司: {result['company'] or '(行业级)'}\n"
                    f"- 标题: {result['title']}\n"
                )
                if result["compiled_pages"]:
                    summary += f"\n已编译到 wiki:\n" + "\n".join(f"- {p}" for p in result["compiled_pages"])
                self.memory.add_turn(question, "ingest_confirm", summary)
                yield _evt("synthesis_chunk", {"text": summary})
            except Exception as e:
                yield _evt("synthesis_chunk", {"text": f"收录失败: {e}"})
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
        async for evt in self.research_service.run(task):
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
            industry=task.industry,
            companies=task.companies,
        )

        yield _evt("synthesis_chunk", {"text": synthesis})

        pending_status = []
        await self.knowledge_service.persist_report(report, on_status=lambda msg: pending_status.append(msg))
        for msg in pending_status:
            yield _evt("status", {"message": msg})

        yield _evt("done", {"total_tokens": total_tokens})
