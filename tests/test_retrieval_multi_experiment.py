import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "evals/components/RETRIEVAL-MULTI/retrieval_policy.py"
SPEC = importlib.util.spec_from_file_location("retrieval_policy", MODULE_PATH)
policy = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(policy)


def test_query_plan_validation_blocks_leaks_and_duplicates():
    valid = {"strategy": "decomposed", "queries": [
        {"query": "Google 成立年份", "target": "Google年份", "entities": ["Google"]},
        {"query": "Athlon 首次发布年份", "target": "Athlon年份", "entities": ["Athlon"]},
    ]}
    assert policy.validate_query_plan(valid, "decomposed") == []
    valid["queries"][1]["query"] = "wiki/concepts/Athlon.md S1"
    assert policy.validate_query_plan(valid, "decomposed")


def test_rrf_merge_is_deterministic_and_rewards_multiple_hits():
    ranked, evidence = policy.rrf_merge([["a", "b"], ["b", "c"]])
    assert ranked == ["b", "a", "c"]
    assert evidence["b"]["hits"] == 2


def test_rerank_does_not_change_candidate_set():
    paths = ["a.md", "b.md", "c.md"]
    tokens = [["苹果", "公司"], ["香蕉", "公司"], ["足球"]]
    ranked, scores = policy.rerank_candidates(paths, tokens, ["a.md", "b.md"], ["苹果"], limit=2)
    assert ranked[0] == "a.md"
    assert set(ranked) == {"a.md", "b.md"}
    assert set(scores) == {"a.md", "b.md"}


def test_arm_c_and_a_share_identical_candidates():
    docs = [("a.md", "苹果 公司"), ("b.md", "苹果 水果"), ("c.md", "足球")]
    tokens = [["苹果", "公司"], ["苹果", "水果"], ["足球"]]
    plan = policy.single_plan("苹果公司")
    arm_a = policy.run_arm("A", "苹果公司", plan, docs, tokens)
    arm_c = policy.run_arm("C", "苹果公司", plan, docs, tokens)
    assert arm_a["candidate_sha256"] == arm_c["candidate_sha256"]
    assert arm_a["candidates"] == arm_c["candidates"]
