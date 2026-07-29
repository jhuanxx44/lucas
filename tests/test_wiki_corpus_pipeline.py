import importlib.util
import json
from pathlib import Path

import pytest


_MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts/wiki_corpus_common.py"
_SPEC = importlib.util.spec_from_file_location("wiki_corpus_common", _MODULE_PATH)
corpus = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(corpus)


def _source(doc_id="concept-semiconductor", url="https://example.com/semiconductor"):
    return {
        "doc_id": doc_id,
        "target_path": "concepts/半导体.md",
        "domain": "半导体",
        "page_type": "concept",
        "source_tier": 2,
        "urls": [url],
        "reason": "覆盖半导体基础定义",
    }


def test_validate_source_plan_accepts_unique_https_entries():
    entries = [
        _source(),
        {
            **_source("company-tsmc", "https://example.com/tsmc"),
            "target_path": "companies/半导体/台积电.md",
            "page_type": "company",
        },
    ]

    assert corpus.validate_source_plan(entries) == []


@pytest.mark.parametrize(
    "mutator, expected",
    [
        (lambda rows: rows.append(dict(rows[0])), "duplicate doc_id"),
        (lambda rows: rows[0].update(urls=["http://example.com"]), "must use https"),
        (lambda rows: rows[0].update(target_path="../escape.md"), "unsafe target_path"),
        (lambda rows: rows[0].update(source_tier=4), "source_tier"),
        (lambda rows: rows.append({**rows[0], "doc_id": "other", "target_path": "concepts/其他.md"}), "duplicate source URL"),
    ],
)
def test_validate_source_plan_rejects_invalid_entries(mutator, expected):
    entries = [_source()]
    mutator(entries)

    assert any(expected in error for error in corpus.validate_source_plan(entries))


def test_snapshot_record_uses_content_hash(tmp_path):
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(json.dumps({
        "markdown": "# 半导体\n\n正文",
        "metadata": {"title": "半导体", "sourceURL": "https://example.com"},
    }), encoding="utf-8")

    record = corpus.snapshot_record(_source(), snapshot, "2026-07-27T00:00:00Z")

    assert record["status"] == "ok"
    assert record["markdown_chars"] == 9
    assert len(record["content_sha256"]) == 64
    assert record["source_url"] == "https://example.com"


def test_validate_wiki_page_requires_sources_for_numeric_claims(tmp_path):
    page = tmp_path / "半导体.md"
    page.write_text("""---
title: 半导体
type: concept
as_of: 2026-07-27
summary: 半导体是现代电子产业的基础材料。
source_ids: [S1]
---

# 半导体

该产业在 2025 年达到 1000 亿元规模。

## 来源

- [S1] 来源 — https://example.com（抓取日期：2026-07-27）
""", encoding="utf-8")

    errors = corpus.validate_wiki_page(page, {"S1"})

    assert any("numeric claim lacks source marker" in error for error in errors)


def test_validate_wiki_page_accepts_grounded_page(tmp_path):
    page = tmp_path / "半导体.md"
    page.write_text("""---
title: 半导体
type: concept
as_of: 2026-07-27
summary: 半导体是现代电子产业的基础材料。
source_ids: [S1]
---

# 半导体

该产业在 2025 年达到 1000 亿元规模。[S1]

## 来源

- [S1] 来源 — https://example.com（抓取日期：2026-07-27）
""", encoding="utf-8")

    assert corpus.validate_wiki_page(page, {"S1"}) == []


def test_validate_wiki_page_does_not_treat_numeric_title_as_claim(tmp_path):
    page = tmp_path / "5G.md"
    page.write_text("""---
title: 5G
type: concept
as_of: 2026-07-27
summary: 第五代移动通信技术。
source_ids: [S1]
---

# 5G

第五代移动通信技术用于移动网络。[S1]

## 来源

- [S1] 来源 — https://example.com（抓取日期：2026-07-27）
""", encoding="utf-8")

    assert corpus.validate_wiki_page(page, {"S1"}) == []


def test_materialize_manifest_copies_only_visible_pages_and_rebuilds_index(tmp_path):
    master = tmp_path / "master/wiki"
    (master / "concepts").mkdir(parents=True)
    (master / "concepts/半导体.md").write_text("semiconductor", encoding="utf-8")
    (master / "concepts/光纤.md").write_text("fiber", encoding="utf-8")
    (master / "concepts/隐藏页面.md").write_text("hidden", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "corpus_version": "wiki-scale-v1",
        "track": "controlled",
        "task_id": "Q01",
        "seed": 1,
        "size": 2,
        "documents": ["concepts/半导体.md", "concepts/光纤.md"],
    }), encoding="utf-8")
    destination = tmp_path / "workspace/wiki"

    result = corpus.materialize_manifest(master, manifest, destination)

    assert result["document_count"] == 2
    assert (destination / "concepts/半导体.md").is_file()
    assert (destination / "concepts/光纤.md").is_file()
    assert not (destination / "concepts/隐藏页面.md").exists()
    index = (destination / "index.md").read_text(encoding="utf-8")
    assert "半导体" in index and "光纤" in index
    assert "隐藏页面" not in index


def test_validator_can_bind_an_explicit_source_plan():
    validator_path = Path(__file__).resolve().parents[1] / "scripts/validate_wiki_corpus.py"
    text = validator_path.read_text(encoding="utf-8")

    assert 'parser.add_argument("--plan", type=Path)' in text
    assert 'plan_path.read_bytes()' in text


def test_prune_corpus_requires_apply_before_removing(tmp_path):
    module_path = Path(__file__).resolve().parents[1] / "scripts/prune_wiki_corpus.py"
    spec = importlib.util.spec_from_file_location("prune_wiki_corpus", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    root = tmp_path / "corpus"
    master = root / "master/wiki"
    (master / "concepts").mkdir(parents=True)
    (master / "concepts/keep.md").write_text("keep", encoding="utf-8")
    (master / "concepts/stale.md").write_text("stale", encoding="utf-8")
    plan = root / "plan.jsonl"
    plan.write_text(json.dumps({"target_path": "concepts/keep.md"}) + "\n", encoding="utf-8")

    dry = module.prune_corpus(root, plan)
    assert dry["unexpected_pages"] == ["concepts/stale.md"]
    assert (master / "concepts/stale.md").is_file()

    applied = module.prune_corpus(root, plan, apply=True)
    assert applied["removed_pages"] == ["concepts/stale.md"]
    assert not (master / "concepts/stale.md").exists()
