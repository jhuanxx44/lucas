import importlib.util
from pathlib import Path


_MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts/review_wiki_corpus.py"
_SPEC = importlib.util.spec_from_file_location("review_wiki_corpus", _MODULE_PATH)
review = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(review)


def _page(path: Path, title: str, domain: str, body: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"""---
title: {title}
type: concept
industry: {domain}
as_of: 2026-07-27
summary: {title}摘要。
source_ids: [S1]
---

# {title}

{body}

## 来源

- [S1] source
""", encoding="utf-8")


def test_extract_claims_prioritizes_numeric_claims(tmp_path):
    page = tmp_path / "wiki/半导体.md"
    _page(page, "半导体", "半导体", "普通事实描述足够长，可以作为候选。[S1]\n\n2025 年市场达到 100 亿元。[S1]")

    claims = review.extract_claims(page, claim_count=3)

    assert claims[0] == "半导体摘要。"
    assert "2025" in claims[1]


def test_select_review_sample_spreads_across_domains(tmp_path):
    master = tmp_path / "master"
    _page(master / "a/一.md", "一", "半导体", "这是第一条足够长的事实描述。[S1]")
    _page(master / "a/二.md", "二", "半导体", "这是第二条足够长的事实描述。[S1]")
    _page(master / "b/三.md", "三", "光通信", "这是第三条足够长的事实描述。[S1]")

    selected = review.select_review_sample(master, 2)
    domains = {review._frontmatter_and_body(page)[0]["industry"] for page in selected}

    assert domains == {"半导体", "光通信"}
