"""write_file 对 wiki 页面 frontmatter 的校验：错误分类、引号规则与豁免场景。"""
from pathlib import Path

from harness.tools.generic.filesystem import WRITE_FILE_SPEC, write_file
from harness.tools.registry import ToolRuntime
from utils.wiki_core import recall_wiki

WIKI_PATH = "wiki/reports/综合/报告.md"


def _unquoted_summary_content() -> str:
    # 摘要未加引号且含英文冒号+空格（《Situational Awareness: The Decade Ahead》），
    # 复刻 2026-07-31 线上 trace 的真实失败内容。
    return (
        "---\n"
        "title: 杠杆与新纪元信仰：从费雪到 Aschenbrenner\n"
        "date: 2026-08-01\n"
        "tags: [杠杆, 风险管理]\n"
        "summary: 2026 年 7 月 30 日，AI 主题对冲基金 Situational Awareness LP 因约 4 倍杠杆"
        "触发追保螺旋。本报告复盘其长文《Situational Awareness: The Decade Ahead》核心论点。\n"
        "---\n\n"
        "# 标题\n"
    )


def _quoted_summary_content() -> str:
    return (
        "---\n"
        "title: 杠杆与新纪元信仰：从费雪到 Aschenbrenner\n"
        "date: 2026-08-01\n"
        "tags: [杠杆, 风险管理]\n"
        "summary: '2026 年 7 月 30 日，AI 主题对冲基金 Situational Awareness LP 因约 4 倍杠杆"
        "触发追保螺旋。本报告复盘其长文《Situational Awareness: The Decade Ahead》核心论点。'\n"
        "---\n\n"
        "# 标题\n"
    )


def test_write_file_rejects_unquoted_summary_as_invalid_yaml(tmp_path: Path):
    result = write_file(tmp_path, {"path": WIKI_PATH, "content": _unquoted_summary_content()})
    assert result.status == "invalid_input"
    assert result.error_code == "invalid_yaml"
    assert "YAML 解析失败" in result.observation
    assert "单引号" in result.observation
    assert "位置" in result.observation


def test_write_file_accepts_quoted_summary(tmp_path: Path):
    result = write_file(tmp_path, {"path": WIKI_PATH, "content": _quoted_summary_content()})
    assert result.ok
    assert (tmp_path / WIKI_PATH).is_file()


def test_write_file_rejects_missing_summary(tmp_path: Path):
    content = "---\ntitle: 标题\n---\n\n正文"
    result = write_file(tmp_path, {"path": "wiki/companies/通信/公司.md", "content": content})
    assert result.status == "invalid_input"
    assert result.error_code == "missing_summary"


def test_write_file_rejects_empty_summary(tmp_path: Path):
    content = "---\ntitle: 标题\nsummary: ''\n---\n\n正文"
    result = write_file(tmp_path, {"path": "wiki/companies/通信/公司.md", "content": content})
    assert result.status == "invalid_input"
    assert result.error_code == "missing_summary"


def test_write_file_rejects_missing_frontmatter(tmp_path: Path):
    result = write_file(tmp_path, {"path": "wiki/companies/通信/公司.md", "content": "# 无 frontmatter"})
    assert result.status == "invalid_input"
    assert result.error_code == "missing_frontmatter"


def test_write_file_skips_validation_outside_wiki(tmp_path: Path):
    result = write_file(tmp_path, {"path": "tmp/note.md", "content": "# 无 frontmatter"})
    assert result.ok


def test_write_file_skips_validation_for_index_and_glossary(tmp_path: Path):
    for name in ("index.md", "glossary.md"):
        result = write_file(tmp_path, {"path": f"wiki/{name}", "content": "# 索引"})
        assert result.ok


async def test_write_file_via_tool_runtime_classifies_yaml_error(tmp_path: Path):
    runtime = ToolRuntime(tmp_path, [WRITE_FILE_SPEC])
    result = await runtime.execute(
        "write_file",
        {"path": WIKI_PATH, "content": _unquoted_summary_content()},
        ["write_file"],
    )
    assert result.error_code == "invalid_yaml"
    assert "YAML 解析失败" in result.observation


def test_written_wiki_page_is_recallable_via_summary(tmp_path: Path):
    result = write_file(tmp_path, {"path": WIKI_PATH, "content": _quoted_summary_content()})
    assert result.ok
    pages = recall_wiki(str(tmp_path / "wiki"), "杠杆 追保螺旋", max_chars=500)
    assert pages
    assert pages[0]["source"] == "summary"
