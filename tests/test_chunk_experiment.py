"""chunk 大小对照实验的确定性单元测试。

只覆盖不依赖 ollama 服务的纯函数：切分、文档级归约、指标计算、批次预算。
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "evals" / "components" / "RETRIEVAL-CHUNK" / "run_chunk_experiment.py"

spec = importlib.util.spec_from_file_location("chunk_exp", SCRIPT)
chunk_exp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(chunk_exp)


def test_chunk_text_respects_size_and_overlap():
    text = "甲" * 1000
    pieces = chunk_exp.chunk_text(text, 400)
    assert all(len(p) <= 400 for p in pieces)
    # 15% 重叠 => step=340，1000 字符应切出 3 片
    assert len(pieces) == 3


def test_chunk_text_whole_page_truncates_at_limit():
    text = "乙" * 10000
    pieces = chunk_exp.chunk_text(text, 0)
    assert len(pieces) == 1
    assert len(pieces[0]) == chunk_exp.PAGE_TRUNCATE_CHARS


def test_chunk_text_drops_tiny_tail():
    # step=255，第二片为 text[255:280] 共 25 字符，短于 40 应被丢弃
    pieces = chunk_exp.chunk_text("丙" * 280, 300)
    assert len(pieces) == 1
    # 对照：残片够长时保留（text[255:350] 共 95 字符）
    assert len(chunk_exp.chunk_text("丙" * 350, 300)) == 2


def test_rank_docs_reduces_to_document_level():
    # 两篇文档各两个 chunk；docB 的某个 chunk 与查询完全同向
    owners = ["a.md", "a.md", "b.md", "b.md"]
    vecs = [[1.0, 0.0], [0.9, 0.1], [0.0, 1.0], [0.2, 0.8]]
    norms = [chunk_exp.math.sqrt(sum(x * x for x in v)) for v in vecs]
    ranked = chunk_exp.rank_docs([0.0, 1.0], vecs, norms, owners)
    # 归约后每篇文档只出现一次，且 b.md 排第一
    assert ranked == ["b.md", "a.md"]
    assert len(ranked) == len(set(ranked))


def test_embed_all_batches_within_char_budget(monkeypatch):
    seen: list[list[str]] = []

    def fake_embed(texts, model, retries=3):
        seen.append(list(texts))
        return [[0.0] for _ in texts]

    monkeypatch.setattr(chunk_exp, "embed", fake_embed)
    # 每条 2500 字符，预算 6000 => 每批最多 2 条
    texts = ["丁" * 2500 for _ in range(5)]
    out = chunk_exp.embed_all(texts, "m")
    assert len(out) == 5
    assert all(
        sum(len(t) for t in batch) <= chunk_exp.BATCH_CHAR_BUDGET or len(batch) == 1
        for batch in seen
    )
    assert max(len(b) for b in seen) <= chunk_exp.MAX_BATCH_ITEMS


def test_embed_all_keeps_oversized_single_item():
    # 单条就超预算时不能丢弃，必须单独成批
    calls: list[list[str]] = []
    chunk_exp_embed = chunk_exp.embed
    try:
        chunk_exp.embed = lambda t, m, retries=3: (calls.append(list(t)), [[0.0]] * len(t))[1]
        out = chunk_exp.embed_all(["戊" * 9000, "己" * 100], "m")
    finally:
        chunk_exp.embed = chunk_exp_embed
    assert len(out) == 2
    assert calls[0] == ["戊" * 9000]


def test_queries_ground_truth_paths_exist():
    data = json.loads((SCRIPT.parent / "queries.json").read_text())
    wiki = ROOT / "wiki"
    missing = [
        g
        for q in data["queries"]
        for g in q["ground_truth"]
        if not (wiki / g).exists()
    ]
    assert missing == []


@pytest.mark.parametrize("qtype", ["point", "section", "cross_doc"])
def test_queries_cover_all_answer_spans(qtype):
    data = json.loads((SCRIPT.parent / "queries.json").read_text())
    assert any(q["type"] == qtype for q in data["queries"])
