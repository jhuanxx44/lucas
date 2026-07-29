import importlib.util
from pathlib import Path


_SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "evals/components/RETRIEVAL-BM25/run_controlled_experiment.py"
)
_SPEC = importlib.util.spec_from_file_location("controlled_retrieval_experiment", _SCRIPT)
experiment = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(experiment)


def test_build_trial_corpus_keeps_ground_truth_and_is_deterministic():
    all_paths = [f"doc-{i}.md" for i in range(12)]
    ground_truth = ["doc-1.md", "doc-7.md"]

    first = experiment.build_trial_corpus(
        all_paths, ground_truth, target_size=6, query_id="q01", trial=3,
    )
    repeated = experiment.build_trial_corpus(
        all_paths, ground_truth, target_size=6, query_id="q01", trial=3,
    )

    assert first == repeated
    assert len(first) == 6
    assert set(ground_truth) <= set(first)


def test_build_trial_corpus_changes_distractors_across_trials():
    all_paths = [f"doc-{i}.md" for i in range(30)]
    ground_truth = ["doc-1.md", "doc-7.md"]

    first = experiment.build_trial_corpus(
        all_paths, ground_truth, target_size=8, query_id="q01", trial=0,
    )
    second = experiment.build_trial_corpus(
        all_paths, ground_truth, target_size=8, query_id="q01", trial=1,
    )

    assert set(first) != set(second)


def test_cluster_bootstrap_resamples_queries_not_individual_trials():
    differences = {
        "q01": [0.2, 0.4],
        "q02": [0.0, 0.2],
        "q03": [-0.1, 0.1],
    }

    result = experiment.cluster_bootstrap(differences, samples=500, seed=7)

    assert result["estimate"] == 0.133333
    assert result["ci_low"] <= result["estimate"] <= result["ci_high"]
    assert result == experiment.cluster_bootstrap(differences, samples=500, seed=7)


def test_exact_sign_flip_test_reports_two_sided_probability():
    result = experiment.exact_sign_flip_pvalue({
        "q01": [0.2, 0.2],
        "q02": [0.1, 0.1],
        "q03": [0.3, 0.3],
    })

    assert result == 0.25


def test_llm_keywords_are_tokenized_before_controlled_comparison():
    tokens = experiment.controlled_query_tokens({
        "query": "unused",
        "llm_keywords": ["全球晶圆代工", "工艺水平"],
    }, mode="llm")

    assert "全球" in tokens
    assert "晶圆" in tokens
    assert "代工" in tokens
    assert "工艺水平" in tokens


def test_rank_both_excludes_zero_score_documents_for_both_algorithms():
    tfidf, bm25 = experiment.rank_both(
        ["a.md", "b.md"],
        [["半导体"], ["光纤"]],
        ["不存在的词"],
    )

    assert tfidf == []
    assert bm25 == []
