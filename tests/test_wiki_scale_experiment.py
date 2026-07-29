import importlib.util
from pathlib import Path


def _load(name: str):
    path = Path(__file__).resolve().parents[1] / f"scripts/{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _page(path: Path, title: str, domain: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"""---
title: {title}
type: concept
industry: {domain}
as_of: 2026-07-27
summary: {title}摘要
source_ids: [S1]
---

# {title}
""", encoding="utf-8")


def test_query_page_selection_is_deterministic_and_stratified(tmp_path):
    module = _load("build_wiki_queries")
    master = tmp_path / "wiki"
    _page(master / "a/1.md", "一", "甲")
    _page(master / "a/2.md", "二", "甲")
    _page(master / "b/3.md", "三", "乙")

    first = module.select_pages(master, 2)
    second = module.select_pages(master, 2)

    assert first == second
    assert {module._frontmatter(path)["industry"] for path in first} == {"甲", "乙"}


def test_query_batch_validation_enforces_type_and_evidence_counts():
    module = _load("build_wiki_queries")
    allowed = {"a.md", "b.md"}
    rows = []
    for query_type in module.TYPE_PATTERN:
        count = 0 if query_type == "insufficient_evidence" else (2 if query_type == "cross_document" else 1)
        rows.append({
            "query": "问题", "type": query_type, "answer": "答案",
            "relevant_paths": ["a.md", "b.md"][:count],
        })

    assert module._valid_batch({"queries": rows}, allowed)
    rows[0]["relevant_paths"] = []
    assert not module._valid_batch({"queries": rows}, allowed)


def test_query_grade_validation_normalizes_exact_candidate_set():
    module = _load("grade_wiki_queries")
    result = {"judgments": [
        {"path": "a.md", "grade": 3}, {"path": "b.md", "grade": 0},
    ]}

    assert module._valid_result(result, ["a.md", "b.md"])
    normalized = module._normalize_result(result, ["b.md", "a.md"])
    assert [row["path"] for row in normalized["judgments"]] == ["b.md", "a.md"]
    assert not module._valid_result(result, ["a.md", "missing.md"])
    assert module._valid_partial(result, ["a.md", "b.md", "missing.md"])


def test_manifest_stratified_order_is_deterministic(tmp_path):
    module = _load("generate_wiki_manifests")
    master = tmp_path / "wiki"
    _page(master / "a/1.md", "一", "甲")
    _page(master / "a/2.md", "二", "甲")
    _page(master / "b/3.md", "三", "乙")
    paths = ["a/1.md", "a/2.md", "b/3.md"]

    first = module.stratified_order(paths, master, "seed")
    second = module.stratified_order(paths, master, "seed")

    assert first == second
    assert set(first) == set(paths)


def test_scale_metrics_use_graded_relevance():
    module = _load("run_wiki_scale_experiment")
    judgments = {"a.md": 3, "b.md": 2, "noise.md": 0}

    assert module.metric(["noise.md", "a.md"], judgments, "recall@5") == 0.5
    assert module.metric(["noise.md", "a.md"], judgments, "mrr") == 0.5
    assert module.metric([], {}, "recall@5") is None


def test_scale_experiment_requires_cached_llm_keywords():
    module = _load("run_wiki_scale_experiment")

    assert module.query_keywords({"id": "Q1", "llm_keywords": ["南亚科技", "DDR5"]}) == ["南亚科技", "DDR5"]
    try:
        module.query_keywords({"id": "Q1", "query": "自然语言问句"})
    except ValueError as exc:
        assert "missing cached llm_keywords" in str(exc)
    else:
        raise AssertionError("NL-only query must be rejected")


def test_keyword_output_requires_two_to_eight_unique_strings():
    module = _load("extract_wiki_query_keywords")

    assert module.parse_keywords({"keywords": ["南亚科技", "DDR5", "低功耗内存", "DDR5"]}) == [
        "南亚科技", "DDR5", "低功耗内存",
    ]
    assert module.parse_keywords({"keywords": ["Internet Explorer", "IE"]}) == ["Internet Explorer", "IE"]
    assert module.parse_keywords({"keywords": ["太少"]}) == []


def test_substring_retrievers_filter_zero_scores():
    module = _load("run_wiki_scale_experiment")
    docs = [("a.md", "半导体 半导体"), ("b.md", "足球")]

    assert module.substring_rank(docs, ["半导体"], "substr_bm25") == ["a.md"]
    assert module.substring_rank(docs, ["半导体"], "substr_tfidf") == ["a.md"]


def test_agent_scale_tasks_have_deterministic_outcomes():
    module = _load("run_wiki_agent_experiment")

    assert set(module.TASKS) == {"QS-023", "QS-029", "QS-059"}
    assert all(value["fact_groups"] and value["evidence_paths"] for value in module.TASKS.values())
    combined = module.score_answer("QS-023", {
        "query_id": "QS-023",
        "facts": ["DDR4、DDR5及低功耗DRAM"],
        "evidence_paths": ["wiki/companies/半导体/南亞科技.md"],
    })
    assert combined["outcome_passed"] is True


def test_agent_scale_builds_a_runnable_task_spec(tmp_path):
    module = _load("run_wiki_agent_experiment")

    task = module._task_spec(tmp_path, {
        "query": "南亚科技的主要产品包括哪些类型的动态随机存取存储器？",
    }, "QS-023")

    assert task.id == "QS-023"
    assert task.allowed_tools == ["wiki_recall"]
    assert task.limits.max_steps == 3


def test_agent_tfidf_tokenizes_compound_keyword_phrases_like_documents(tmp_path):
    module = _load("run_wiki_agent_experiment")
    page = tmp_path / "wiki/companies/食品饮料/奥德瓦拉.md"
    page.parent.mkdir(parents=True)
    page.write_text("# 奥德瓦拉\n\n奥德瓦拉公司成立于1980年。", encoding="utf-8")

    result = module.tfidf_wiki_recall(tmp_path, {
        "query": "奥德瓦拉公司, 南亚科技, 成立年份",
    })

    assert result.status == "ok"
    assert "companies/食品饮料/奥德瓦拉.md" in result.observation
