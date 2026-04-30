import glob
import json
import logging
import os
import re
import shutil
from dataclasses import asdict
from datetime import date

from agents.models import Claim, Evidence, ManagerReport
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

        status("正在生成证据和结论索引...")
        try:
            await self.write_sidecars(report, report_dir)
        except Exception as e:
            logger.warning("生成 sidecar 失败: %s", e)

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

    def build_evidence(self, report: ManagerReport) -> list[Evidence]:
        evidence: list[Evidence] = []

        def next_id() -> str:
            return f"ev_{len(evidence) + 1:03d}"

        for r in report.results:
            issue_messages = []
            if r.verification:
                issue_messages = [i.message for i in r.verification.issues]

            for idx, source in enumerate(r.source_urls, start=1):
                url = source.get("url", "")
                title = source.get("title", "") or url
                issues = [m for m in issue_messages if url and url in m]
                if issues:
                    status = "warning"
                elif r.verification:
                    status = "verified"
                else:
                    status = "unverified"
                evidence.append(Evidence(
                    id=next_id(),
                    source_id=f"{r.researcher_id}:source:{idx}",
                    kind="source",
                    subject=title,
                    text=title,
                    path_or_url=url,
                    snippet=title,
                    reliability="medium",
                    verification_status=status,
                    issues=issues,
                ))

            if r.market_data.strip():
                issues = [
                    i.message for i in (r.verification.issues if r.verification else [])
                    if i.dimension == "data_crosscheck"
                ]
                if any("严重偏差" in issue for issue in issues):
                    status = "error"
                elif issues:
                    status = "warning"
                elif r.verification:
                    status = "verified"
                else:
                    status = "unverified"
                evidence.append(Evidence(
                    id=next_id(),
                    source_id=f"{r.researcher_id}:market_data",
                    kind="metric",
                    subject=f"{r.researcher_name} 市场数据",
                    text=r.market_data,
                    snippet=r.market_data[:500],
                    reliability="high",
                    verification_status=status,
                    issues=issues,
                ))

            if r.verification:
                for idx, issue in enumerate(r.verification.issues, start=1):
                    evidence.append(Evidence(
                        id=next_id(),
                        source_id=f"{r.researcher_id}:verification:{idx}",
                        kind="verification_issue",
                        subject=issue.dimension,
                        text=issue.message,
                        reliability="medium",
                        verification_status=issue.severity,
                        issues=[issue.message],
                    ))

        return evidence

    async def extract_claims(self, report: ManagerReport, evidence: list[Evidence]) -> tuple[str, list[Claim], str]:
        evidence_summary = "\n".join(
            f"- {e.id} [{e.kind}/{e.verification_status}] {e.subject}: {e.snippet or e.text[:200]}"
            for e in evidence[:30]
        ) or "（暂无 evidence）"

        prompt = self._load_prompt("claim-extract").format(
            question=report.question,
            synthesis=report.synthesis[:6000],
            evidence_summary=evidence_summary,
        )
        text, _ = await self.client.chat(
            prompt=prompt,
            response_mime_type="application/json",
            temperature=0.1,
        )
        data = extract_json(text)
        if data is None:
            return "error", [], "claim-extract JSON 解析失败"

        raw_claims = data if isinstance(data, list) else data.get("claims", [])
        if not isinstance(raw_claims, list):
            return "error", [], "claim-extract 返回格式不是 claims 列表"

        evidence_ids = {e.id for e in evidence}
        claims = []
        for idx, raw in enumerate(raw_claims[:20], start=1):
            if not isinstance(raw, dict):
                continue
            text = str(raw.get("text", "")).strip()
            if not text:
                continue
            raw_evidence_ids = raw.get("evidence_ids", [])
            if not isinstance(raw_evidence_ids, list):
                raw_evidence_ids = []
            linked_ids = [
                eid for eid in raw_evidence_ids
                if isinstance(eid, str) and eid in evidence_ids
            ]
            confidence = raw.get("confidence", "medium")
            if confidence not in ("high", "medium", "low", "unverified"):
                confidence = "medium"
            if not linked_ids and confidence != "unverified":
                confidence = "low"
            claim_type = raw.get("type", "interpretation")
            if claim_type not in ("fact", "interpretation", "forecast", "risk", "assumption"):
                claim_type = "interpretation"
            assumptions = raw.get("assumptions", [])
            if not isinstance(assumptions, list):
                assumptions = []
            claims.append(Claim(
                id=f"cl_{idx:03d}",
                type=claim_type,
                text=text,
                evidence_ids=linked_ids,
                confidence=confidence,
                assumptions=[str(a) for a in assumptions],
            ))

        status = "ok" if claims else "empty"
        return status, claims, ""

    async def write_sidecars(self, report: ManagerReport, report_dir: str):
        evidence = self.build_evidence(report)
        evidence_payload = {
            "version": 1,
            "status": "ok",
            "evidence": [asdict(e) for e in evidence],
        }
        with open(os.path.join(report_dir, "evidence.json"), "w", encoding="utf-8") as f:
            json.dump(evidence_payload, f, ensure_ascii=False, indent=2)

        claims_status = "error"
        claims: list[Claim] = []
        error = ""
        try:
            claims_status, claims, error = await self.extract_claims(report, evidence)
        except Exception as e:
            logger.warning("提取 claims 失败: %s", e)
            error = str(e)

        claims_payload = {
            "version": 1,
            "status": claims_status,
            "claims": [asdict(c) for c in claims],
        }
        if error:
            claims_payload["error"] = error
        with open(os.path.join(report_dir, "claims.json"), "w", encoding="utf-8") as f:
            json.dump(claims_payload, f, ensure_ascii=False, indent=2)

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

    def _list_company_categories(self) -> str:
        companies_dir = os.path.join(_WIKI_DIR, "companies")
        if not os.path.isdir(companies_dir):
            return "（暂无）"
        lines = []
        for cat in sorted(os.listdir(companies_dir)):
            cat_path = os.path.join(companies_dir, cat)
            if not os.path.isdir(cat_path) or cat.startswith("."):
                continue
            names = sorted(
                f.replace(".md", "") for f in os.listdir(cat_path) if f.endswith(".md")
            )
            if names:
                lines.append(f"- {cat}（{len(names)}家）：{', '.join(names)}")
        return "\n".join(lines) if lines else "（暂无）"

    def _list_wiki_pages(self) -> str:
        lines = []
        companies_dir = os.path.join(_WIKI_DIR, "companies")
        if os.path.isdir(companies_dir):
            for cat in sorted(os.listdir(companies_dir)):
                cat_path = os.path.join(companies_dir, cat)
                if not os.path.isdir(cat_path) or cat.startswith("."):
                    continue
                for fname in sorted(os.listdir(cat_path)):
                    if fname.endswith(".md"):
                        lines.append(f"- companies/{cat}/{fname}")

        for subdir in ("industries", "concepts"):
            base = os.path.join(_WIKI_DIR, subdir)
            if not os.path.isdir(base):
                continue
            for fname in sorted(os.listdir(base)):
                if fname.endswith(".md"):
                    lines.append(f"- {subdir}/{fname}")

        return "\n".join(lines) if lines else "（暂无）"

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

    def _find_existing_company(self, name: str) -> str | None:
        pattern = os.path.join(_WIKI_DIR, "companies", "*", f"{name}.md")
        matches = glob.glob(pattern)
        return matches[0] if matches else None

    def _page_path(self, page_type: str, name: str, industry: str = "") -> str:
        type_to_dir = {
            "company": "companies",
            "industry": "industries",
            "concept": "concepts",
        }
        subdir = type_to_dir.get(page_type, page_type)
        if page_type == "company":
            existing = self._find_existing_company(name)
            if existing:
                return existing
            if industry:
                return os.path.join(_WIKI_DIR, subdir, industry, f"{name}.md")
        return os.path.join(_WIKI_DIR, subdir, f"{name}.md")

    def _validate_wiki_content(self, new_content: str, old_content: str = "") -> str | None:
        """校验 LLM 产出的 wiki 页面。返回 None 表示通过，返回 str 表示拒绝原因。"""
        if not new_content.startswith("---"):
            return "缺少 frontmatter（不以 --- 开头）"
        match = re.match(r"^---\n(.+?)\n---", new_content, re.DOTALL)
        if not match:
            return "frontmatter 未闭合"
        fm = match.group(1)
        for field in ("title", "type", "updated"):
            if not re.search(rf"^{field}\s*:", fm, re.MULTILINE):
                return f"frontmatter 缺少必要字段: {field}"

        if old_content and old_content.startswith("---"):
            old_sections = set(re.findall(r"^## (.+)$", old_content, re.MULTILINE))
            new_sections = set(re.findall(r"^## (.+)$", new_content, re.MULTILINE))
            lost = old_sections - new_sections
            if lost:
                logger.warning("wiki 更新丢失了以下段落: %s", ", ".join(sorted(lost)))

        return None

    @staticmethod
    def _backup_file(path: str):
        if os.path.isfile(path):
            shutil.copy2(path, path + ".bak")

    async def _plan_wiki_updates(self, report: ManagerReport) -> list[dict]:
        prompt = self._load_prompt("wiki-plan").format(
            synthesis=report.synthesis,
            existing_pages=self._list_wiki_pages(),
            company_categories=self._list_company_categories(),
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

                old_content = ""
                if os.path.isfile(page_path):
                    with open(page_path, "r", encoding="utf-8") as f:
                        old_content = f.read()

                error = self._validate_wiki_content(new_content, old_content)
                if error:
                    logger.warning("wiki 内容校验失败 %s/%s: %s", page_type, name, error)
                    status(f"  ✗ {page_type}/{name}: 校验失败 — {error}")
                    continue

                self._backup_file(page_path)
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
                company_categories=self._list_company_categories(),
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

                # 从 raw 路径提取行业: raw/{行业}/... 或 raw/sources/{行业}/...
                parts = rel_path.split("/")
                if len(parts) > 2 and parts[1] == "sources":
                    raw_industry = parts[2] if len(parts) > 3 else "未分类"
                else:
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

                    error = self._validate_wiki_content(new_content, current_content if action == "update" else "")
                    if error:
                        logger.warning("编译内容校验失败 %s/%s: %s", page_type, name, error)
                        status(f"  ✗ {page_type}/{name}: 校验失败 — {error}")
                        continue

                    self._backup_file(page_path)
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

    async def classify_source(self, content: str) -> dict:
        """用 LLM 对材料做轻量分类，返回 {title, industry, company, confidence, alternatives}。"""
        prompt = self._load_prompt("source-classify").format(
            content=content[:2000],
        )
        text, _ = await self.client.chat(
            prompt=prompt,
            response_mime_type="application/json",
            temperature=0.1,
        )
        result = extract_json(text)
        if result is None:
            return {"title": "未命名材料", "industry": "未分类", "company": "", "confidence": "high", "alternatives": []}
        return {
            "title": result.get("title", "未命名材料"),
            "industry": result.get("industry", "未分类"),
            "company": result.get("company", ""),
            "confidence": result.get("confidence", "high"),
            "alternatives": result.get("alternatives", []),
        }

    async def ingest_source(
        self,
        content: str,
        title: str,
        industry: str,
        url: str = "",
        company: str = "",
        on_status=None,
    ) -> dict:
        """
        存储已确认的材料并编译进 wiki。
        返回 {"path", "industry", "company", "title", "compiled_pages"}.
        """
        def status(msg):
            if on_status:
                on_status(msg)

        today = date.today().isoformat()
        slug = self._make_slug(title)

        if company:
            dest_dir = os.path.join(_RAW_DIR, "sources", industry, company)
        else:
            dest_dir = os.path.join(_RAW_DIR, "sources", industry)
        os.makedirs(dest_dir, exist_ok=True)

        filename = f"{today}_{slug}.md"
        file_path = os.path.join(dest_dir, filename)

        if not content.startswith("---\n"):
            frontmatter = f"---\nsource: {url or 'user-input'}\ntitle: {title}\ndate: {today}\ntype: {'url' if url else 'text'}\nindustry: {industry}\ncompany: {company}\n---\n\n"
            content = frontmatter + content

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        rel_path = os.path.relpath(file_path, _PROJECT_ROOT)
        status(f"已保存: {rel_path}")

        status("正在编译到 wiki...")
        compile_plan = {"scope": "specific", "sources": [rel_path]}
        compile_summary = await self.compile_from_raw(compile_plan, on_status=on_status)

        compiled_pages = []
        for line in compile_summary.split("\n"):
            if line.startswith("- "):
                compiled_pages.append(line[2:])

        return {
            "path": rel_path,
            "industry": industry,
            "company": company,
            "title": title,
            "compiled_pages": compiled_pages,
        }
