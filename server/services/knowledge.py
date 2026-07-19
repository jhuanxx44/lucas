"""wiki 知识模块：classify-source / ingest-source 的服务实现（M5 重建）。

替代 agents/knowledge_service.py 中收录/编译相关的职责（M6 删除旧实现）。
设计思想见 docs/plans/2026-07-20-single-mode-rewrite.md 第 3 节：

1. 四层存储边界：raw/ 只读（本模块绝不写）→ ingested/ 收录落盘 →
   reports/ 归档（随旧 manager 链路退役，本模块不写）→ wiki/ 编译视图。
2. 来源与页面分离：ingested 材料补 frontmatter（source/title/date/type/industry/company）；
   wiki 页面 frontmatter 的 sources 声明编译来源；已编译检测靠扫描 wiki
   页面 frontmatter（yaml 解析），不维护编译状态数据库。
3. Plan → Compile 两段式：LLM 先输出结构化 JSON 计划，再按计划逐页编译。
4. 写入前确定性校验（frontmatter 必填 title/type/updated、旧段落丢失检测）
   + 写前 .bak 备份——代码保证，不靠 prompt。
5. 增量更新语义写进 prompts/wiki-compile.md 契约（保留旧内容、新增标注日期、
   矛盾并存标注时间）。
6. 收录两段确认：classify（LLM 提议 + confidence + alternatives）→ 用户确认
   → ingest（落盘 ingested/{行业}/{公司}/{日期}_{slug}.md + 定向编译该来源）。
7. 索引维护：wiki/index.md 结构化重建（解析现有条目 + 合并新条目重新生成，
   不用 str.replace 占位符替换）。

领域本体（行业列表、索引标题）在 lucas.yaml 的 wiki 段维护，不进代码。
"""
import glob
import json
import logging
import os
import re
import shutil
from datetime import date
from typing import AsyncGenerator

import yaml

from harness.config import WikiConfig, load_wiki_config
from harness.runner import load_prompt_template
from utils.json_extract import extract_json
from utils.llm_client import create_client
from utils.wiki_core import parse_index_entries

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
_PROMPTS_DIR = os.path.join(_PROJECT_ROOT, "prompts")

_PAGE_TYPES = ("company", "industry", "concept")
_PAGE_TYPE_DIRS = {"company": "companies", "industry": "industries", "concept": "concepts"}
_REQUIRED_FRONTMATTER = ("title", "type", "updated")
# 索引分节的规范排序：已知前缀在前，未知分节保持原文件中的先后顺序
_SECTION_PREFIX_ORDER = ("公司档案", "行业概览", "概念/主题", "分析报告")

_CLASSIFY_FALLBACK = {
    "title": "未命名材料",
    "industry": "未分类",
    "company": "",
    "confidence": "low",
    "alternatives": [],
}


def split_frontmatter(text: str) -> tuple[dict, str]:
    """yaml 解析 frontmatter，返回 (frontmatter, body)；无法解析时返回 ({}, 原文)。"""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    try:
        fm = yaml.safe_load(text[3:end])
    except yaml.YAMLError:
        return {}, text
    return (fm if isinstance(fm, dict) else {}), text[end + 4:]


_FENCE_RE = re.compile(r"```(?:json)?\s*\n(.*?)```", re.DOTALL)


def _extract_loose_json(text: str):
    """脏 JSON 容错：先走 utils.extract_json，再尝试围栏代码块 / 首尾括号切片。"""
    data = extract_json(text)
    if data is not None:
        return data
    for match in _FENCE_RE.finditer(text):
        data = extract_json(match.group(1))
        if data is not None:
            return data
    start = len(text)
    for ch in "{[":
        idx = text.find(ch)
        if idx != -1:
            start = min(start, idx)
    if start < len(text):
        end = max(text.rfind("}"), text.rfind("]"))
        if end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass
    return None


def parse_classification(text: str) -> dict:
    """解析 classify LLM 返回（容错脏 JSON），输出契约固定的分类结果。"""
    data = _extract_loose_json(text)
    if not isinstance(data, dict):
        return dict(_CLASSIFY_FALLBACK)

    def _str_field(key: str, default: str) -> str:
        value = data.get(key)
        return value.strip() if isinstance(value, str) and value.strip() else default

    confidence = data.get("confidence")
    if confidence not in ("high", "low"):
        confidence = "low"

    alternatives = []
    raw_alts = data.get("alternatives")
    if isinstance(raw_alts, list):
        for alt in raw_alts:
            if isinstance(alt, dict) and isinstance(alt.get("industry"), str) and alt["industry"].strip():
                alternatives.append({
                    "industry": alt["industry"].strip(),
                    "reason": str(alt.get("reason", "")),
                })
            if len(alternatives) >= 2:
                break
    if confidence == "high":
        alternatives = []

    return {
        "title": _str_field("title", "未命名材料"),
        "industry": _str_field("industry", "未分类"),
        "company": _str_field("company", ""),
        "confidence": confidence,
        "alternatives": alternatives,
    }


def validate_plan(data) -> list[dict]:
    """校验 plan JSON：只保留合法条目（type/name 必填，action 缺省 create）。"""
    if not isinstance(data, list):
        return []
    plans = []
    for item in data:
        if not isinstance(item, dict):
            continue
        page_type = item.get("type")
        name = item.get("name")
        if page_type not in _PAGE_TYPES or not isinstance(name, str) or not name.strip():
            continue
        action = item.get("action")
        plans.append({
            "type": page_type,
            "name": name.strip(),
            "action": action if action in ("create", "update") else "create",
            "reason": str(item.get("reason", "")),
        })
    return plans


def ensure_source_in_frontmatter(content: str, source_path: str) -> str:
    """代码保证本来源路径进入 frontmatter sources（LLM 漏写则补上），不靠 prompt 自觉。

    sources 已含该路径时原样返回（逐字节不变）；缺 frontmatter 时原样返回，
    交由 validate_page 确定性拦截。
    """
    fm, body = split_frontmatter(content)
    if not fm:
        return content
    sources = fm.get("sources")
    if isinstance(sources, str):
        sources = [sources]
    elif not isinstance(sources, list):
        sources = []
    sources = [str(s) for s in sources]
    if source_path in sources:
        return content
    fm = {**fm, "sources": [*sources, source_path]}
    dumped = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False)
    return f"---\n{dumped}---{body}"


def validate_page(content: str, old_content: str = "") -> tuple[str | None, list[str]]:
    """写入前确定性校验。返回 (拒绝原因, 丢失的旧段落列表)；拒绝原因 None 表示通过。"""
    if not content.startswith("---"):
        return "缺少 frontmatter（不以 --- 开头）", []
    fm, _ = split_frontmatter(content)
    if not fm:
        return "frontmatter 未闭合或无法解析", []
    for field in _REQUIRED_FRONTMATTER:
        if not fm.get(field):
            return f"frontmatter 缺少必要字段: {field}", []

    lost: list[str] = []
    if old_content:
        old_sections = set(re.findall(r"^## (.+)$", old_content, re.MULTILINE))
        new_sections = set(re.findall(r"^## (.+)$", content, re.MULTILINE))
        lost = sorted(old_sections - new_sections)
    return None, lost


def rebuild_index(wiki_root: str, new_entries: list[dict], title: str = "Lucas 知识库索引"):
    """结构化重建 wiki/index.md：解析现有条目 + 合并新条目，整体重新生成。

    new_entries: [{"section": "公司档案 · 电子", "name": "页面名", "path": "companies/电子/x.md"}]
    同 path 的条目去重（以新 name 覆盖）；分节按规范顺序排列，未知分节保持原顺序。
    """
    index_path = os.path.join(wiki_root, "index.md")
    grouped: dict[str, dict[str, str]] = {}  # section -> {path: name}（保持插入序）
    order: list[str] = []
    for entry in parse_index_entries(index_path):
        section = entry["section"] or "其他"
        if section not in grouped:
            grouped[section] = {}
            order.append(section)
        grouped[section][entry["path"]] = entry["name"]
    for entry in new_entries:
        section = entry["section"]
        if section not in grouped:
            grouped[section] = {}
            order.append(section)
        grouped[section][entry["path"]] = entry["name"]

    def _sort_key(section: str):
        for i, prefix in enumerate(_SECTION_PREFIX_ORDER):
            if section == prefix or section.startswith(f"{prefix} ·"):
                return (i, section)
        return (len(_SECTION_PREFIX_ORDER), str(order.index(section)))

    lines = [f"# {title}", ""]
    for section in sorted(grouped, key=_sort_key):
        lines.append(f"## {section}")
        for path, name in grouped[section].items():
            lines.append(f"- [{name}]({path})")
        lines.append("")

    with open(index_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).rstrip() + "\n")


def _safe_segment(name: str, default: str = "未分类") -> str:
    """路径段消毒：去掉路径分隔符和前导点，防止 LLM/用户输入逃逸目录。"""
    cleaned = name.replace("/", "_").replace("\\", "_").strip().strip(".")
    return cleaned or default


def _make_slug(title: str) -> str:
    slug = re.sub(r'[\\/:*?"<>|\s]+', "_", title).strip("._")
    return (slug or "untitled")[:40]


class KnowledgeService:
    """wiki 收录与编译：classify（轻量分类）+ ingest（落盘 + 定向编译）。"""

    def __init__(self, client, workspace, config: WikiConfig | None = None,
                 prompts_dir: str | None = None):
        self.client = client
        self._ws = workspace
        self._config = config or WikiConfig()
        self._prompts_dir = prompts_dir or _PROMPTS_DIR
        self._wiki_dir = workspace.wiki_root
        self._ingested_dir = workspace.ingested_root

    # ── prompt 加载 ──────────────────────────────────────

    def _prompt(self, name: str) -> str:
        return load_prompt_template(os.path.join(self._prompts_dir, f"{name}.md"))

    def _industries_text(self) -> str:
        if not self._config.industries:
            return "（未配置，自行判断行业名称）"
        return "、".join(self._config.industries)

    # ── classify ─────────────────────────────────────────

    async def classify_source(self, content: str) -> dict:
        """LLM 轻量分类，返回 {title, industry, company, confidence, alternatives}。"""
        prompt = self._prompt("source-classify").format(
            content=content[:2000],
            industries=self._industries_text(),
        )
        text, _ = await self.client.chat(
            prompt=prompt,
            response_mime_type="application/json",
            temperature=0.1,
        )
        return parse_classification(text)

    # ── ingest（异步生成器，逐步产出 SSE 事件） ────────────

    async def ingest_source(
        self,
        content: str,
        title: str,
        industry: str,
        url: str = "",
        company: str = "",
    ) -> AsyncGenerator[tuple[str, dict], None]:
        """落盘 ingested/ 并定向编译进 wiki，逐步 yield (event, data)。

        事件序列：status* → saved → status* → compiled → done；异常 → error。
        """
        try:
            yield ("status", {"message": "正在保存原始材料..."})
            rel_path = self._save_source(content, title, industry, url, company)
            yield ("saved", {"path": rel_path})

            compiled_pages: list[str] = []

            # 声明式溯源：该来源已在某 wiki 页面 sources 中则跳过重复编译（幂等）
            if rel_path in self._compiled_sources():
                yield ("status", {"message": "该来源此前已编译过，跳过重复编译"})
            else:
                yield ("status", {"message": "正在规划 wiki 更新..."})
                plans = await self._plan(rel_path, content)
                if not plans:
                    yield ("status", {"message": "本次材料无需更新 wiki 页面"})
                else:
                    yield ("status", {"message": f"需要更新 {len(plans)} 个 wiki 页面"})
                    new_entries = []
                    async for event, data in self._compile_plans(plans, rel_path, content, industry):
                        if event == "_compiled":
                            compiled_pages.append(data["page"])
                            new_entries.append(data["entry"])
                        else:
                            yield (event, data)
                    if new_entries:
                        yield ("status", {"message": "正在重建 wiki 索引..."})
                        rebuild_index(self._wiki_dir, new_entries, title=self._config.index_title)

            yield ("compiled", {"pages": compiled_pages})
            yield ("done", {
                "path": rel_path,
                "industry": industry,
                "company": company,
                "title": title,
                "compiled_pages": compiled_pages,
            })
        except Exception as e:
            logger.exception("ingest-source error: %s", title)
            yield ("error", {"message": str(e)})

    # ── 落盘 ─────────────────────────────────────────────

    def _save_source(self, content: str, title: str, industry: str,
                     url: str, company: str) -> str:
        """写入 ingested/{行业}/{公司}/{日期}_{slug}.md 并补 frontmatter，返回工作区相对路径。"""
        today = date.today().isoformat()
        industry_seg = _safe_segment(industry)
        parts = [self._ingested_dir, industry_seg]
        if company.strip():
            parts.append(_safe_segment(company))
        dest_dir = os.path.join(*parts)
        os.makedirs(dest_dir, exist_ok=True)

        file_path = os.path.join(dest_dir, f"{today}_{_make_slug(title)}.md")

        if not content.startswith("---\n"):
            frontmatter = yaml.safe_dump({
                "source": url or "user-input",
                "title": title,
                "date": today,
                "type": "url" if url else "text",
                "industry": industry,
                "company": company,
            }, allow_unicode=True, sort_keys=False)
            content = f"---\n{frontmatter}---\n\n{content}"

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        return os.path.relpath(file_path, self._ws.root).replace(os.sep, "/")

    # ── Plan → Compile ───────────────────────────────────

    async def _plan(self, source_path: str, source_content: str) -> list[dict]:
        prompt = self._prompt("wiki-plan").format(
            source_path=source_path,
            source_content=source_content[:self._config.source_max_chars],
            industries=self._industries_text(),
            existing_pages=self._list_wiki_pages(),
            company_categories=self._list_company_categories(),
        )
        text, _ = await self.client.chat(
            prompt=prompt,
            response_mime_type="application/json",
            temperature=0.3,
        )
        plans = validate_plan(_extract_loose_json(text))
        if not plans:
            logger.info("wiki plan 为空或解析失败: %s", (text or "")[:200])
        return plans

    async def _compile_plans(
        self, plans: list[dict], source_path: str, source_content: str, industry: str
    ) -> AsyncGenerator[tuple[str, dict], None]:
        """逐页编译；单页失败不阻断其他页面。编译成功 yield ("_compiled", {...})。"""
        for plan in plans:
            label = f"{plan['type']}/{plan['name']}"
            yield ("status", {"message": f"  {'创建' if plan['action'] == 'create' else '更新'} {label}..."})
            try:
                page_path = self._page_path(plan["type"], plan["name"], industry)
                old_content = ""
                if os.path.isfile(page_path):
                    with open(page_path, "r", encoding="utf-8") as f:
                        old_content = f.read()

                new_content = await self._compile_page(plan, source_path, source_content, old_content)
                # 代码保证本来源进入 frontmatter sources（幂等溯源不靠 LLM 自觉）
                new_content = ensure_source_in_frontmatter(new_content, source_path)

                error, lost = validate_page(new_content, old_content if old_content else "")
                if error:
                    logger.warning("wiki 内容校验失败 %s: %s", label, error)
                    yield ("status", {"message": f"  ✗ {label}: 校验失败 — {error}"})
                    continue
                if lost:
                    logger.warning("wiki 更新丢失旧段落 %s: %s", label, ", ".join(lost))
                    yield ("status", {"message": f"  ⚠ {label}: 丢失旧段落（{', '.join(lost)}），仍按校验通过写入"})

                self._backup_file(page_path)
                os.makedirs(os.path.dirname(page_path), exist_ok=True)
                with open(page_path, "w", encoding="utf-8") as f:
                    f.write(new_content)

                rel_wiki = os.path.relpath(page_path, self._wiki_dir).replace(os.sep, "/")
                entry = {
                    "section": self._index_section(plan["type"], rel_wiki, industry),
                    "name": plan["name"],
                    "path": rel_wiki,
                }
                yield ("status", {"message": f"  ✓ {label}"})
                yield ("_compiled", {"page": f"{plan['action']}: {label}", "entry": entry})
            except Exception as e:
                logger.warning("编译 wiki 页面失败 %s: %s", label, e)
                yield ("status", {"message": f"  ✗ {label}: {e}"})

    async def _compile_page(self, plan: dict, source_path: str,
                            source_content: str, old_content: str) -> str:
        action = plan["action"] if old_content else "create"
        if action == "create":
            task_desc = f"根据收录材料创建新的 {plan['type']} 页面：{plan['name']}"
            current_content = "（新页面，尚无内容）"
        else:
            task_desc = f"根据收录材料增量更新 {plan['type']} 页面：{plan['name']}。原因：{plan['reason']}"
            current_content = old_content

        prompt = self._prompt("wiki-compile").format(
            current_content=current_content,
            source_content=source_content[:self._config.source_max_chars],
            task_desc=task_desc,
            today=date.today().isoformat(),
            source_path=source_path,
        )
        text, _ = await self.client.chat(prompt=prompt, temperature=0.3)
        return text

    # ── wiki 页面定位 / 校验辅助 ──────────────────────────

    def _page_path(self, page_type: str, name: str, industry: str = "") -> str:
        name = _safe_segment(name, default="untitled")
        if page_type == "company":
            # 同一公司不得出现在多个分类下：已有页面优先复用其位置
            pattern = os.path.join(self._wiki_dir, "companies", "*", f"{glob.escape(name)}.md")
            matches = glob.glob(pattern)
            if matches:
                return matches[0]
            if industry:
                return os.path.join(self._wiki_dir, "companies", _safe_segment(industry), f"{name}.md")
            return os.path.join(self._wiki_dir, "companies", f"{name}.md")
        return os.path.join(self._wiki_dir, _PAGE_TYPE_DIRS[page_type], f"{name}.md")

    @staticmethod
    def _index_section(page_type: str, rel_wiki: str, industry: str) -> str:
        if page_type == "company":
            # 以页面实际所在分类目录为准（已有页面可能在别的分类下）
            parts = rel_wiki.split("/")
            if len(parts) == 3:
                return f"公司档案 · {parts[1]}"
            return f"公司档案 · {_safe_segment(industry)}"
        if page_type == "industry":
            return "行业概览"
        return "概念/主题"

    @staticmethod
    def _backup_file(path: str):
        if os.path.isfile(path):
            shutil.copy2(path, path + ".bak")

    def _compiled_sources(self) -> set[str]:
        """声明式溯源：扫描 wiki 页面 frontmatter 的 sources 字段（yaml 解析）。"""
        compiled: set[str] = set()
        for md_path in glob.glob(os.path.join(self._wiki_dir, "**", "*.md"), recursive=True):
            try:
                with open(md_path, "r", encoding="utf-8") as f:
                    fm, _ = split_frontmatter(f.read())
            except OSError:
                continue
            sources = fm.get("sources")
            if isinstance(sources, list):
                compiled.update(str(s) for s in sources)
            elif isinstance(sources, str):
                compiled.add(sources)
        return compiled

    def _list_company_categories(self) -> str:
        companies_dir = os.path.join(self._wiki_dir, "companies")
        if not os.path.isdir(companies_dir):
            return "（暂无）"
        lines = []
        for cat in sorted(os.listdir(companies_dir)):
            cat_path = os.path.join(companies_dir, cat)
            if not os.path.isdir(cat_path) or cat.startswith("."):
                continue
            names = sorted(f.replace(".md", "") for f in os.listdir(cat_path) if f.endswith(".md"))
            if names:
                lines.append(f"- {cat}（{len(names)}家）：{', '.join(names)}")
        return "\n".join(lines) if lines else "（暂无）"

    def _list_wiki_pages(self) -> str:
        lines = []
        companies_dir = os.path.join(self._wiki_dir, "companies")
        if os.path.isdir(companies_dir):
            for cat in sorted(os.listdir(companies_dir)):
                cat_path = os.path.join(companies_dir, cat)
                if not os.path.isdir(cat_path) or cat.startswith("."):
                    continue
                for fname in sorted(os.listdir(cat_path)):
                    if fname.endswith(".md"):
                        lines.append(f"- companies/{cat}/{fname}")
        for subdir in ("industries", "concepts"):
            base = os.path.join(self._wiki_dir, subdir)
            if not os.path.isdir(base):
                continue
            for fname in sorted(os.listdir(base)):
                if fname.endswith(".md"):
                    lines.append(f"- {subdir}/{fname}")
        return "\n".join(lines) if lines else "（暂无）"


def create_knowledge_service(workspace, config_path: str | None = None) -> KnowledgeService:
    """正常 service 构造：lucas.yaml wiki 段 → LLM client → KnowledgeService。"""
    config = load_wiki_config(config_path)
    client = create_client(provider=config.provider, model=config.model)
    return KnowledgeService(client, workspace, config)
