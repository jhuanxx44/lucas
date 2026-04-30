import glob
import json
import logging
import os
from datetime import date

from agents.models import ManagerReport
from utils.json_extract import extract_json
from utils.source_collector import collect_sources

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
_WIKI_DIR = os.path.join(_PROJECT_ROOT, "wiki")
_RAW_DIR = os.path.join(_PROJECT_ROOT, "raw")
_PROMPTS_DIR = os.path.join(_PROJECT_ROOT, "prompts")


class KnowledgeService:
    """知识库服务：负责报告归档、wiki 更新、raw 编译和记忆持久化。"""

    def __init__(self, client, memory, prompt_loader):
        self.client = client
        self.memory = memory
        self._load_prompt = prompt_loader

    def _make_slug(self, question: str) -> str:
        slug = question.replace(" ", "_").replace("/", "_").replace("?", "").replace("？", "")
        return slug[:40]

    async def persist_report(self, report: ManagerReport, on_status=None):
        def status(msg):
            if on_status:
                on_status(msg)

        status("正在生成报告标题...")
        report.title = await self.generate_title(report.question, report.synthesis)
        status("正在归档分析结果...")
        report_dir = self.archive(report)

        all_urls = report.unique_urls()
        if all_urls:
            collected = await collect_sources(
                all_urls, report.industry, report.companies, on_status=status,
            )
            if collected and report_dir:
                meta_path = os.path.join(report_dir, "meta.json")
                try:
                    with open(meta_path, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                    meta["collected_sources"] = [
                        {"title": c["title"], "url": c["url"], "path": c["path"]}
                        for c in collected
                    ]
                    with open(meta_path, "w", encoding="utf-8") as f:
                        json.dump(meta, f, ensure_ascii=False, indent=2)
                except Exception as e:
                    logger.warning("回写 collected_sources 到 meta.json 失败: %s", e)

        status("正在整理 wiki 知识库...")
        await self.update_wiki(report, on_status=on_status)

        self.memory.add_turn(report.question, "research", report.synthesis)
        status("正在提取分析结论...")
        await self.extract_and_save_conclusion(report)
        await self.extract_and_save_preferences(report.question, report.synthesis)

    async def generate_title(self, question: str, synthesis: str) -> str:
        try:
            prompt = self._load_prompt("title-extract").format(
                question=question,
                synthesis=synthesis[:500],
            )
            title, _ = await self.client.chat(prompt=prompt, temperature=0.1)
            title = title.strip().strip('"').strip("'").strip("《》")
            if 3 <= len(title) <= 40:
                return title
        except Exception as e:
            logger.warning("生成报告标题失败: %s", e)
        return question[:40]

    async def extract_and_save_conclusion(self, report: ManagerReport):
        try:
            prompt = self._load_prompt("conclusion-extract").format(
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

    async def extract_and_save_preferences(self, question: str, synthesis: str):
        try:
            current = self.memory.load_preferences()
            prompt = self._load_prompt("preference-extract").format(
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

    def archive(self, report: ManagerReport) -> str:
        """归档报告，返回 report_dir 路径。"""
        today = date.today().isoformat()
        title = report.title or report.question[:40]
        slug = self._make_slug(title)
        industry = report.industry or "未分类"
        companies = report.companies or []

        # 目录结构：有公司放公司下，无公司放行业下
        if companies:
            report_dir = os.path.join(_RAW_DIR, industry, companies[0], f"{today}_{slug}")
        else:
            report_dir = os.path.join(_RAW_DIR, industry, f"{today}_{slug}")
        os.makedirs(report_dir, exist_ok=True)

        # 写各研究员报告
        for r in report.results:
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
            path = os.path.join(report_dir, f"{r.researcher_id}.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)

        # 写 meta.json
        all_urls = report.unique_urls()

        meta = {
            "question": report.question,
            "title": title,
            "date": today,
            "industry": industry,
            "companies": companies,
            "researchers": [
                {"id": r.researcher_id, "name": r.researcher_name, "model": r.model}
                for r in report.results
            ],
            "source_urls": all_urls,
        }
        with open(os.path.join(report_dir, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        # wiki 综合报告
        report_rel = os.path.relpath(report_dir, _PROJECT_ROOT)
        wiki_dir = os.path.join(_WIKI_DIR, "reports", industry)
        os.makedirs(wiki_dir, exist_ok=True)
        wiki_filename = f"{today}_{slug}.md"
        wiki_path = os.path.join(wiki_dir, wiki_filename)

        sources = "\n".join(
            f"  - {report_rel}/{r.researcher_id}.md"
            for r in report.results
        )
        researchers_list = ", ".join(
            f"{r.researcher_name}({r.model})" for r in report.results
        )

        ref_section = ""
        if all_urls:
            ref_section = (
                "\n\n## 参考资料\n"
                + "\n".join(f"- [{u['title']}]({u['url']})" for u in all_urls)
                + "\n"
            )

        confidences = [r.confidence for r in report.results]
        if "low" in confidences:
            overall_confidence = "low"
        elif all(c == "high" for c in confidences):
            overall_confidence = "high"
        else:
            overall_confidence = "medium"

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
            f"title: {title}\n"
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

        self._update_index(wiki_filename, title, industry)
        logger.info("归档完成: %s + wiki/reports/%s/%s", report_rel, industry, wiki_filename)
        return report_dir

    def _update_index(self, wiki_filename: str, question: str, industry: str):
        index_path = os.path.join(_PROJECT_ROOT, "wiki", "index.md")
        entry = f"- [{question}](reports/{industry}/{wiki_filename})"

        try:
            with open(index_path, "r", encoding="utf-8") as f:
                content = f.read()
        except FileNotFoundError:
            content = "# Lucas A股股市 Wiki 索引\n"

        if wiki_filename in content:
            return

        section_header = f"## 分析报告 · {industry}"
        if section_header not in content:
            content = content.rstrip() + f"\n\n{section_header}\n{entry}\n"
        else:
            content = content.replace(section_header, f"{section_header}\n{entry}", 1)

        with open(index_path, "w", encoding="utf-8") as f:
            f.write(content)

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

    def _page_path(self, page_type: str, name: str, industry: str = "") -> str:
        type_to_dir = {
            "company": "companies",
            "industry": "industries",
            "concept": "concepts",
        }
        subdir = type_to_dir.get(page_type, page_type)
        if page_type == "company" and industry:
            return os.path.join(_WIKI_DIR, subdir, industry, f"{name}.md")
        return os.path.join(_WIKI_DIR, subdir, f"{name}.md")

    async def _plan_wiki_updates(self, report: ManagerReport) -> list[dict]:
        prompt = self._load_prompt("wiki-plan").format(
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
        page_path = self._page_path(page_type, name, industry=report.industry)

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

        all_urls = report.unique_urls()
        source_urls_text = "\n".join(
            f"- [{u['title']}]({u['url']})" for u in all_urls
        ) if all_urls else "（无外部来源）"

        today = date.today().isoformat()
        prompt = self._load_prompt("wiki-compile").format(
            template=template,
            current_content=current_content,
            synthesis=report.synthesis,
            source_urls=source_urls_text,
            task_desc=task_desc,
            today=today,
        )
        text, _ = await self.client.chat(prompt=prompt, temperature=0.3)
        return text

    async def update_wiki(self, report: ManagerReport, on_status=None):
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
                industry = report.industry or "未分类"
                page_path = self._page_path(page_type, name, industry=industry)
                os.makedirs(os.path.dirname(page_path), exist_ok=True)
                with open(page_path, "w", encoding="utf-8") as f:
                    f.write(new_content)

                type_to_section = {
                    "company": f"## 公司档案 · {industry}",
                    "industry": "## 行业概览",
                    "concept": "## 概念/主题",
                }
                section = type_to_section.get(page_type)
                if section:
                    type_to_dir = {"company": "companies", "industry": "industries", "concept": "concepts"}
                    if page_type == "company":
                        rel_path = f"{type_to_dir[page_type]}/{industry}/{name}.md"
                    else:
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

    def _find_compiled_sources(self) -> set[str]:
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
        if compile_plan.get("scope") == "specific" and compile_plan.get("sources"):
            paths = []
            for src in compile_plan["sources"]:
                full = os.path.join(_PROJECT_ROOT, src)
                if os.path.isfile(full):
                    paths.append(full)
            return paths

        compiled = self._find_compiled_sources()
        meta_dirs = set()
        for meta_path in glob.glob(os.path.join(_RAW_DIR, "**", "meta.json"), recursive=True):
            meta_dirs.add(os.path.dirname(meta_path))

        paths = []
        for md_path in sorted(glob.glob(os.path.join(_RAW_DIR, "**", "*.md"), recursive=True)):
            if any(md_path.startswith(d + os.sep) or os.path.dirname(md_path) == d for d in meta_dirs):
                continue
            rel = os.path.relpath(md_path, _PROJECT_ROOT)
            if rel in compiled:
                continue
            paths.append(md_path)
        return paths

    async def compile_from_raw(self, compile_plan: dict, on_status=None) -> str:
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

            classify_prompt = self._load_prompt("raw-classify").format(
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

            for plan in plans:
                page_type = plan.get("type", "")
                name = plan.get("name", "")
                action = plan.get("action", "create")
                if not page_type or not name:
                    continue

                # 从 raw 路径提取行业: raw/{行业}/...
                parts = rel_path.split("/")
                raw_industry = parts[1] if len(parts) > 2 else "未分类"

                template = self._load_template(page_type)
                page_path = self._page_path(page_type, name, industry=raw_industry)

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
                compile_prompt = self._load_prompt("raw-compile").format(
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
                        "company": f"## 公司档案 · {raw_industry}",
                        "industry": "## 行业概览",
                        "concept": "## 概念/主题",
                    }
                    section = type_to_section.get(page_type)
                    if section:
                        type_to_dir = {"company": "companies", "industry": "industries", "concept": "concepts"}
                        if page_type == "company":
                            wiki_rel = f"{type_to_dir[page_type]}/{raw_industry}/{name}.md"
                        else:
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
