import importlib.util
from pathlib import Path

import pytest


_MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts/convert_to_simplified.py"
_SPEC = importlib.util.spec_from_file_location("convert_to_simplified", _MODULE_PATH)
conversion = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(conversion)


def test_convert_text_uses_phrase_aware_traditional_to_simplified_conversion():
    converted = conversion.convert_text("臺灣的軟體著作權與滑鼠，位於臺北。")

    assert converted == "台湾的软体著作权与滑鼠，位于台北。"
    assert conversion.convert_text(converted) == converted


def test_convert_tree_is_dry_run_by_default_and_apply_is_idempotent(tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    page = wiki / "繁體標題.md"
    page.write_text("# 繁體標題\n\n這是一份測試文件。", encoding="utf-8")
    index = wiki / "index.md"
    index.write_text("# 自動生成索引：繁體標題", encoding="utf-8")

    dry_run = conversion.convert_tree(wiki)

    assert dry_run["changed_files"] == 1
    assert "繁體標題" in page.read_text(encoding="utf-8")

    applied = conversion.convert_tree(wiki, apply=True)

    assert applied["changed_files"] == 1
    assert page.read_text(encoding="utf-8") == "# 繁体标题\n\n这是一份测试文件。"
    assert page.name == "繁體標題.md"
    assert "繁體標題" in index.read_text(encoding="utf-8")
    assert conversion.convert_tree(wiki, apply=True)["changed_files"] == 0


def test_convert_tree_refuses_to_modify_raw_inputs(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()

    with pytest.raises(ValueError, match="raw"):
        conversion.convert_tree(raw, apply=True, raw_root=raw)
