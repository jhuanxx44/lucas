"""M5 wiki 知识模块（server/services/knowledge.py）测试。

约束迁移自 tests/test_storage_boundaries.py（原文件 M6 删除）：
- raw/ 快照逐字节不变（本模块绝不写 raw/）
- ingest 只写 ingested/（+ wiki/ 编译产物），不碰 reports/

sidecar（evidence.json/claims.json）机制与旧 manager 的 reports 归档 +
verification 强耦合，ingest 流程用不到，不迁移；"副作用失败降级"约束迁移为：
plan/compile 失败不阻断 saved + done（见 test_ingest_plan_failure_degrades /
test_ingest_validation_failure_still_done）。
"""
import os
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from harness.config import WikiConfig, load_wiki_config
from server.services.knowledge import (
    KnowledgeService,
    ensure_source_in_frontmatter,
    parse_classification,
    rebuild_index,
    split_frontmatter,
    validate_page,
    validate_plan,
)

TODAY = date.today().isoformat()


class FakeClient:
    """按队列返回预置响应的 LLM client。"""

    def __init__(self, responses=None):
        self._responses = list(responses or [])
        self.calls = []

    async def generate_text(self, **kwargs):
        self.calls.append(kwargs)
        if self._responses:
            return self._responses.pop(0), None
        return "", None


def _workspace(tmp_path: Path):
    return SimpleNamespace(
        root=str(tmp_path),
        raw_root=str(tmp_path / "raw"),
        ingested_root=str(tmp_path / "ingested"),
        reports_root=str(tmp_path / "reports"),
        wiki_root=str(tmp_path / "wiki"),
        memory_root=str(tmp_path / "memory"),
    )


def _service(tmp_path: Path, client) -> KnowledgeService:
    ws = _workspace(tmp_path)
    Path(ws.raw_root).mkdir()
    Path(ws.wiki_root).mkdir()
    config = WikiConfig(industries=["电子", "新能源"], index_title="测试索引")
    return KnowledgeService(client, ws, config)


async def _collect(service: KnowledgeService, **kwargs) -> list[tuple[str, dict]]:
    return [event async for event in service.ingest_source(**kwargs)]


def _event_types(events: list[tuple[str, dict]]) -> list[str]:
    return [e for e, _ in events]


def _snapshot(root: str) -> list[tuple[str, bytes]]:
    base = Path(root)
    if not base.is_dir():
        return []
    return [
        (str(p.relative_to(base)), p.read_bytes())
        for p in sorted(base.rglob("*"))
        if p.is_file()
    ]


def _compile_page(rel_source: str, name: str = "宁德时代", extra_sections: str = "") -> str:
    return (
        f"---\n"
        f"title: {name}\n"
        f"type: company\n"
        f"created: {TODAY}\n"
        f"updated: {TODAY}\n"
        f"sources:\n"
        f"  - {rel_source}\n"
        f"---\n\n"
        f"# {name}\n\n"
        f"## 基本信息\n\n动力电池龙头。\n"
        f"{extra_sections}"
    )


PLAN_ONE = (
    '[{"type": "company", "name": "宁德时代", "action": "create", "reason": "新材料"}]'
)


# ── classify 解析（含脏 JSON 容错） ─────────────────────────


def test_parse_classification_clean_json():
    text = '{"title": "宁德时代季报", "industry": "新能源", "company": "宁德时代", "confidence": "high", "alternatives": []}'
    result = parse_classification(text)
    assert result == {
        "title": "宁德时代季报",
        "industry": "新能源",
        "company": "宁德时代",
        "confidence": "high",
        "alternatives": [],
    }


def test_parse_classification_dirty_json():
    # markdown 代码块 + 前后杂质 + 非法 confidence + alternatives 缺字段
    text = (
        '好的，分类结果如下：\n```json\n'
        '{"title": "动力电池行业跟踪", "industry": "新能源", "company": "", '
        '"confidence": "maybe", "alternatives": [{"industry": "电子"}, "junk", {"noinustry": "x"}]}\n'
        '```\n以上。'
    )
    result = parse_classification(text)
    assert result["title"] == "动力电池行业跟踪"
    assert result["industry"] == "新能源"
    assert result["confidence"] == "low"  # 非法值收敛为 low
    assert result["alternatives"] == [{"industry": "电子", "reason": ""}]


def test_parse_classification_non_json_fallback():
    result = parse_classification("完全不是 JSON 的回答")
    assert result["title"] == "未命名材料"
    assert result["industry"] == "未分类"
    assert result["confidence"] == "low"
    assert result["alternatives"] == []


def test_parse_classification_high_confidence_drops_alternatives():
    text = '{"title": "t", "industry": "电子", "confidence": "high", "alternatives": [{"industry": "化工", "reason": "r"}]}'
    assert parse_classification(text)["alternatives"] == []


async def test_classify_source_end_to_end(tmp_path):
    client = FakeClient(['{"title": "季报", "industry": "新能源", "company": "宁德时代", "confidence": "low", "alternatives": [{"industry": "电子", "reason": "交叉"}]}'])
    service = _service(tmp_path, client)

    result = await service.classify_source("宁德时代发布三季度报告……")

    assert result["industry"] == "新能源"
    assert result["confidence"] == "low"
    assert result["alternatives"] == [{"industry": "电子", "reason": "交叉"}]
    # prompt 注入了领域本体行业列表
    assert "电子、新能源" in client.calls[0]["prompt"]


async def test_classify_prompt_includes_existing_wiki_categories(tmp_path):
    """classify 候选 = 配置本体 + wiki 已有分类，让 LLM 收敛到已存在的分类。"""
    client = FakeClient(['{"title": "t", "industry": "光通信", "company": "中际旭创", "confidence": "high", "alternatives": []}'])
    service = _service(tmp_path, client)  # config 只有 电子、新能源
    # wiki 里已存在"光通信"分类（config 本体里没有）
    (Path(service._wiki_dir) / "companies" / "光通信").mkdir(parents=True)

    await service.classify_source("中际旭创光模块业务……")

    prompt = client.calls[0]["prompt"]
    assert "电子" in prompt and "新能源" in prompt  # 配置本体
    assert "光通信" in prompt  # wiki 已有分类被合并进候选


# ── plan JSON 校验 ─────────────────────────────────────────


def test_validate_plan_filters_invalid_entries():
    data = [
        {"type": "company", "name": "宁德时代", "action": "update", "reason": "r"},
        {"type": "stock", "name": "非法类型"},          # 非法 type
        {"type": "industry"},                            # 缺 name
        {"type": "concept", "name": "  "},               # 空 name
        "not a dict",
        {"type": "industry", "name": "新能源"},          # action 缺省 → create
        {"type": "concept", "name": "固态电池", "action": "delete"},  # 非法 action → create
    ]
    plans = validate_plan(data)
    assert plans == [
        {"type": "company", "name": "宁德时代", "action": "update", "reason": "r"},
        {"type": "industry", "name": "新能源", "action": "create", "reason": ""},
        {"type": "concept", "name": "固态电池", "action": "create", "reason": ""},
    ]


def test_validate_plan_non_list_returns_empty():
    assert validate_plan(None) == []
    assert validate_plan({"type": "company"}) == []
    assert validate_plan("[]") == []


# ── frontmatter 必填校验（写入前确定性拦截） ─────────────────


def test_validate_page_accepts_valid_content():
    content = f"---\ntitle: 宁德时代\ntype: company\nupdated: {TODAY}\n---\n\n# 宁德时代\n"
    error, lost = validate_page(content)
    assert error is None
    assert lost == []


def test_validate_page_rejects_missing_frontmatter():
    error, _ = validate_page("# 没有 frontmatter 的正文")
    assert error == "缺少 frontmatter（不以 --- 开头）"


@pytest.mark.parametrize("field", ["title", "type", "updated"])
def test_validate_page_rejects_missing_required_field(field):
    fields = {"title": "宁德时代", "type": "company", "updated": TODAY}
    del fields[field]
    fm = "\n".join(f"{k}: {v}" for k, v in fields.items())
    error, _ = validate_page(f"---\n{fm}\n---\n\n正文\n")
    assert error == f"frontmatter 缺少必要字段: {field}"


def test_validate_page_detects_lost_sections_on_update():
    old = "---\ntitle: t\ntype: company\nupdated: 2026-01-01\n---\n\n## 基本信息\nx\n\n## 财务概况\ny\n"
    new = f"---\ntitle: t\ntype: company\nupdated: {TODAY}\n---\n\n## 基本信息\nx2\n"
    error, lost = validate_page(new, old)
    assert error is None
    assert lost == ["财务概况"]


# ── 索引结构化重建 ─────────────────────────────────────────


def test_rebuild_index_merges_and_orders_sections(tmp_path):
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    index = wiki_dir / "index.md"
    index.write_text(
        "# 旧标题\n\n"
        "## 分析报告 · 电子\n"
        "- [旧报告](reports/电子/2026-01-01_旧报告.md)\n\n"
        "## 自定义分节\n"
        "- [杂项](misc/a.md)\n",
        encoding="utf-8",
    )

    rebuild_index(str(wiki_dir), [
        {"section": "公司档案 · 电子", "name": "宁德时代", "path": "companies/电子/宁德时代.md"},
    ], title="测试索引")

    content = index.read_text(encoding="utf-8")
    assert content.startswith("# 测试索引")
    # 旧条目保留
    assert "- [旧报告](reports/电子/2026-01-01_旧报告.md)" in content
    assert "- [杂项](misc/a.md)" in content
    # 新条目进入正确分节
    assert "## 公司档案 · 电子\n- [宁德时代](companies/电子/宁德时代.md)" in content
    # 规范排序：公司档案 < 分析报告 < 未知分节（保持原顺序）
    assert content.index("## 公司档案 · 电子") < content.index("## 分析报告 · 电子")
    assert content.index("## 分析报告 · 电子") < content.index("## 自定义分节")


def test_rebuild_index_dedupes_by_path(tmp_path):
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()

    entry = {"section": "行业概览", "name": "新能源", "path": "industries/新能源.md"}
    rebuild_index(str(wiki_dir), [entry], title="测试索引")
    rebuild_index(str(wiki_dir), [{"section": "行业概览", "name": "新能源（更新名）", "path": "industries/新能源.md"}], title="测试索引")

    content = (wiki_dir / "index.md").read_text(encoding="utf-8")
    assert content.count("industries/新能源.md") == 1
    assert "新能源（更新名）" in content


# ── ingest 全流程（mock LLM） ───────────────────────────────


async def test_ingest_full_flow_event_sequence(tmp_path):
    rel_source = f"ingested/新能源/宁德时代/{TODAY}_宁德时代季报.md"
    client = FakeClient([PLAN_ONE, _compile_page(rel_source)])
    service = _service(tmp_path, client)

    events = await _collect(
        service,
        content="宁德时代三季度营收增长……",
        title="宁德时代季报",
        industry="新能源",
        company="宁德时代",
        url="https://example.com/report",
    )

    types = _event_types(events)
    assert "error" not in types
    assert types[0] == "status"
    # 事件序列：status* → saved → status* → compiled → done（真逐步产出）
    assert types.index("saved") < types.index("compiled") < types.index("done")
    assert types[-1] == "done"

    # saved：落盘 ingested/{行业}/{公司}/{日期}_{slug}.md
    saved = next(d for e, d in events if e == "saved")
    assert saved["path"] == rel_source
    saved_file = tmp_path / rel_source
    assert saved_file.is_file()
    saved_text = saved_file.read_text(encoding="utf-8")
    # 收录落盘补 frontmatter（source/title/date/type/industry/company）
    assert saved_text.startswith("---\n")
    for field in ("source:", "title:", "date:", "type:", "industry:", "company:"):
        assert field in saved_text.split("---")[1]
    assert "https://example.com/report" in saved_text

    # compiled + done 契约
    compiled = next(d for e, d in events if e == "compiled")
    assert compiled["pages"] == ["create: company/宁德时代"]
    done = next(d for e, d in events if e == "done")
    assert done["path"] == rel_source
    assert done["compiled_pages"] == ["create: company/宁德时代"]

    # wiki 页面写入
    page = tmp_path / "wiki" / "companies" / "新能源" / "宁德时代.md"
    assert page.is_file()

    # 索引重建
    index_text = (tmp_path / "wiki" / "index.md").read_text(encoding="utf-8")
    assert index_text.startswith("# 测试索引")
    assert "## 公司档案 · 新能源" in index_text
    assert "- [宁德时代](companies/新能源/宁德时代.md)" in index_text


async def test_ingest_keeps_raw_immutable_and_reports_untouched(tmp_path):
    """迁移自 test_storage_boundaries：raw 快照逐字节不变；reports 零写入。"""
    ws = _workspace(tmp_path)
    Path(ws.raw_root).mkdir()
    Path(ws.wiki_root).mkdir()
    raw_marker = Path(ws.raw_root) / "user-input.md"
    raw_marker.write_text("immutable", encoding="utf-8")
    before = _snapshot(ws.raw_root)

    client = FakeClient([PLAN_ONE, _compile_page(f"ingested/新能源/宁德时代/{TODAY}_宁德时代季报.md")])
    service = KnowledgeService(client, ws, WikiConfig(industries=["新能源"]))

    events = await _collect(
        service, content="收录内容", title="宁德时代季报", industry="新能源", company="宁德时代",
    )

    assert "error" not in _event_types(events)
    assert _snapshot(ws.raw_root) == before
    assert _snapshot(ws.reports_root) == []


async def test_ingest_backs_up_existing_page_and_warns_lost_sections(tmp_path):
    service = _service(tmp_path, FakeClient())
    page = tmp_path / "wiki" / "companies" / "新能源" / "宁德时代.md"
    page.parent.mkdir(parents=True)
    old_content = (
        "---\ntitle: 宁德时代\ntype: company\nupdated: 2026-01-01\n---\n\n"
        "# 宁德时代\n\n## 基本信息\n\n旧内容。\n\n## 财务概况\n\n旧财务。\n"
    )
    page.write_text(old_content, encoding="utf-8")

    # update 计划 + 新内容丢失了「财务概况」段落 → 警告但仍写入，且写前备份
    rel_source = f"ingested/新能源/宁德时代/{TODAY}_宁德时代季报.md"
    new_content = _compile_page(rel_source)  # 只有「基本信息」段落
    service.client = FakeClient([
        '[{"type": "company", "name": "宁德时代", "action": "update", "reason": "季报"}]',
        new_content,
    ])

    events = await _collect(
        service, content="新材料", title="宁德时代季报", industry="新能源", company="宁德时代",
    )

    types = _event_types(events)
    assert "error" not in types
    statuses = [d["message"] for e, d in events if e == "status"]
    assert any("⚠" in m and "财务概况" in m for m in statuses)
    # 写前 .bak 备份 = 旧内容逐字节
    assert (page.parent / "宁德时代.md.bak").read_text(encoding="utf-8") == old_content
    # 新内容已写入
    assert page.read_text(encoding="utf-8") == new_content


async def test_ingest_validation_failure_blocks_write_but_still_done(tmp_path):
    """frontmatter 校验拦截坏写入；单页失败降级，不阻断 saved + done。"""
    client = FakeClient([PLAN_ONE, "没有 frontmatter 的坏输出"])
    service = _service(tmp_path, client)

    events = await _collect(
        service, content="材料", title="宁德时代季报", industry="新能源", company="宁德时代",
    )

    types = _event_types(events)
    assert "error" not in types
    assert "saved" in types and "done" in types
    statuses = [d["message"] for e, d in events if e == "status"]
    assert any("校验失败" in m for m in statuses)
    compiled = next(d for e, d in events if e == "compiled")
    assert compiled["pages"] == []
    # 坏内容未落盘
    assert not (tmp_path / "wiki" / "companies" / "新能源" / "宁德时代.md").exists()


async def test_ingest_plan_failure_degrades(tmp_path):
    """plan LLM 返回脏数据 → 跳过编译，但 saved + done 正常（副作用失败降级）。"""
    client = FakeClient(["完全不是 JSON"])
    service = _service(tmp_path, client)

    events = await _collect(
        service, content="材料", title="宁德时代季报", industry="新能源",
    )

    types = _event_types(events)
    assert "error" not in types
    assert types.index("saved") < types.index("compiled") < types.index("done")
    done = next(d for e, d in events if e == "done")
    assert done["compiled_pages"] == []
    # 无公司时落盘 ingested/{行业}/
    assert (tmp_path / "ingested" / "新能源" / f"{TODAY}_宁德时代季报.md").is_file()


# ── 声明式溯源（已编译检测靠 wiki 页面 frontmatter sources） ──


def test_ensure_source_appends_missing_source():
    """LLM 漏写 sources → 代码补上；已有 sources 保留"""
    content = (
        "---\ntitle: 宁德时代\ntype: company\nupdated: 2026-01-01\n"
        "sources:\n  - ingested/新能源/a.md\n---\n\n# 宁德时代\n\n正文。\n"
    )
    fixed = ensure_source_in_frontmatter(content, "ingested/新能源/b.md")
    fm, body = split_frontmatter(fixed)
    assert fm["sources"] == ["ingested/新能源/a.md", "ingested/新能源/b.md"]
    assert fm["title"] == "宁德时代"
    assert body == "\n\n# 宁德时代\n\n正文。\n"


def test_ensure_source_no_sources_field():
    """frontmatter 完全没有 sources 字段 → 新建 sources"""
    content = "---\ntitle: t\ntype: company\nupdated: 2026-01-01\n---\n\n正文\n"
    fixed = ensure_source_in_frontmatter(content, "ingested/x.md")
    fm, _ = split_frontmatter(fixed)
    assert fm["sources"] == ["ingested/x.md"]


def test_ensure_source_already_present_returns_unchanged():
    """sources 已含该路径 → 原样返回（逐字节不变）"""
    content = (
        "---\ntitle: t\ntype: company\nupdated: 2026-01-01\n"
        "sources:\n  - ingested/x.md\n---\n\n正文\n"
    )
    assert ensure_source_in_frontmatter(content, "ingested/x.md") == content


def test_ensure_source_no_frontmatter_passthrough():
    """缺 frontmatter 的坏输出原样返回，交给 validate_page 拦截"""
    content = "没有 frontmatter 的坏输出"
    assert ensure_source_in_frontmatter(content, "ingested/x.md") == content


async def test_ingest_guarantees_source_in_page_frontmatter(tmp_path):
    """LLM 编译输出漏写 sources → 落盘页面 frontmatter 仍含本来源路径（幂等溯源）"""
    rel_source = f"ingested/新能源/宁德时代/{TODAY}_宁德时代季报.md"
    page_without_sources = (
        f"---\ntitle: 宁德时代\ntype: company\ncreated: {TODAY}\nupdated: {TODAY}\n---\n\n"
        "# 宁德时代\n\n## 基本信息\n\n动力电池龙头。\n"
    )
    client = FakeClient([PLAN_ONE, page_without_sources])
    service = _service(tmp_path, client)

    events = await _collect(
        service, content="材料", title="宁德时代季报", industry="新能源", company="宁德时代",
    )

    assert "error" not in _event_types(events)
    page = tmp_path / "wiki" / "companies" / "新能源" / "宁德时代.md"
    assert page.is_file()
    fm, body = split_frontmatter(page.read_text(encoding="utf-8"))
    assert rel_source in fm["sources"]
    assert "动力电池龙头" in body


def test_page_path_escapes_glob_chars(tmp_path):
    """页面名含 glob 特殊字符时不会误匹配其他页面"""
    service = _service(tmp_path, FakeClient())
    other = tmp_path / "wiki" / "companies" / "新能源" / "宁德时代.md"
    other.parent.mkdir(parents=True)
    other.write_text("x", encoding="utf-8")
    # "宁德[时]代" 若不 escape，glob 会把它当字符类匹配到 "宁德时代.md"
    path = service._page_path("company", "宁德[时]代", "新能源")
    assert path.endswith("宁德[时]代.md")


def test_compiled_sources_scans_frontmatter(tmp_path):
    service = _service(tmp_path, FakeClient())
    page = tmp_path / "wiki" / "industries" / "新能源.md"
    page.parent.mkdir(parents=True)
    page.write_text(
        "---\ntitle: 新能源\ntype: industry\nupdated: 2026-01-01\n"
        "sources:\n  - ingested/新能源/a.md\n  - ingested/新能源/b.md\n---\n\n正文\n",
        encoding="utf-8",
    )

    assert service._compiled_sources() == {"ingested/新能源/a.md", "ingested/新能源/b.md"}


async def test_ingest_skips_already_compiled_source(tmp_path):
    """同一来源路径已在 wiki 页面 sources 中 → 幂等跳过重复编译。"""
    rel_source = f"ingested/新能源/{TODAY}_行业周报.md"
    service = _service(tmp_path, FakeClient())
    page = tmp_path / "wiki" / "industries" / "新能源.md"
    page.parent.mkdir(parents=True)
    page.write_text(
        f"---\ntitle: 新能源\ntype: industry\nupdated: 2026-01-01\nsources:\n  - {rel_source}\n---\n\n正文\n",
        encoding="utf-8",
    )

    events = await _collect(
        service, content="材料", title="行业周报", industry="新能源",
    )

    types = _event_types(events)
    assert "error" not in types
    statuses = [d["message"] for e, d in events if e == "status"]
    assert any("跳过重复编译" in m for m in statuses)
    assert next(d for e, d in events if e == "compiled")["pages"] == []
    assert service.client.calls == []  # 未发起任何 LLM 调用


# ── 领域配置（lucas.yaml wiki 段） ──────────────────────────


def test_load_wiki_config_reads_wiki_section(tmp_path):
    cfg_path = tmp_path / "lucas.yaml"
    cfg_path.write_text(
        "wiki:\n  model: deepseek-v4-flash\n  index_title: 自定义索引\n  industries: [电子, 新能源]\n",
        encoding="utf-8",
    )
    cfg = load_wiki_config(cfg_path)
    assert cfg.model == "deepseek-v4-flash"
    assert cfg.index_title == "自定义索引"
    assert cfg.industries == ["电子", "新能源"]


def test_load_wiki_config_defaults(tmp_path):
    cfg = load_wiki_config(tmp_path / "不存在.yaml")
    assert cfg.model
    assert cfg.industries == []
    assert cfg.index_title
    assert cfg.source_max_chars > 0
