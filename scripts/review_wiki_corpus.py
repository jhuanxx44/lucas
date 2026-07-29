#!/usr/bin/env python3
"""对冻结 Wiki 母库做分层 LLM 来源支持抽检。"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.compile_wiki_corpus import _clean_snapshot
from scripts.wiki_corpus_common import load_jsonl
from utils.json_extract import extract_json
from utils.llm_client import create_client


DEFAULT_CORPUS = ROOT / "evals/corpora/wiki-scale-v1"
PROMPT_PATH = ROOT / "prompts/evals/wiki-corpus-review.md"


def _frontmatter_and_body(path: Path) -> tuple[dict, str]:
    parts = path.read_text(encoding="utf-8").split("---", 2)
    return yaml.safe_load(parts[1]), parts[2]


def select_review_sample(master: Path, sample_size: int) -> list[Path]:
    pages = sorted(path for path in master.rglob("*.md") if path.name != "index.md")
    by_domain: dict[str, list[Path]] = {}
    for page in pages:
        frontmatter, _ = _frontmatter_and_body(page)
        by_domain.setdefault(frontmatter.get("industry", "unknown"), []).append(page)
    for domain_pages in by_domain.values():
        domain_pages.sort(key=lambda page: hashlib.sha256(
            page.relative_to(master).as_posix().encode()
        ).hexdigest())

    domains = sorted(by_domain, key=lambda domain: (-len(by_domain[domain]), domain))
    selected = []
    while len(selected) < min(sample_size, len(pages)):
        progressed = False
        for domain in domains:
            if by_domain[domain]:
                selected.append(by_domain[domain].pop(0))
                progressed = True
                if len(selected) == sample_size:
                    break
        if not progressed:
            break
    return selected


def extract_claims(page: Path, claim_count: int = 5) -> list[str]:
    frontmatter, body = _frontmatter_and_body(page)
    claims = [frontmatter["summary"]]
    content = body.split("\n## 来源", 1)[0]
    sentences = []
    for line in content.splitlines():
        line = re.sub(r"\[S\d+\]", "", line).strip()
        if not line or line.startswith("#") or re.fullmatch(r"\|?\s*[:|\- ]+\|?", line):
            continue
        if line.startswith("|"):
            sentences.append(line)
        else:
            sentences.extend(
                sentence.strip() for sentence in re.split(r"(?<=[。！？])", line)
                if len(sentence.strip()) >= 15
            )
    numeric = [sentence for sentence in sentences if any(char.isdigit() for char in sentence)]
    non_numeric = [sentence for sentence in sentences if sentence not in numeric]
    for sentence in numeric + non_numeric:
        if sentence not in claims:
            claims.append(sentence)
        if len(claims) == claim_count:
            break
    return claims


async def review_corpus(corpus_root: Path, sample_size: int, workers: int,
                        plan_path: Path | None = None) -> dict:
    master = corpus_root / "master/wiki"
    plan_path = plan_path or corpus_root / "source-plan.jsonl"
    plan = {entry["target_path"]: entry for entry in load_jsonl(plan_path)}
    catalog = load_jsonl(corpus_root / "sources/catalog.jsonl")
    records_by_doc: dict[str, list[dict]] = {}
    for record in catalog:
        if record.get("status") == "ok":
            records_by_doc.setdefault(record["doc_id"], []).append(record)

    prompt_text = PROMPT_PATH.read_text(encoding="utf-8")
    if prompt_text.startswith("---\n"):
        prompt_text = prompt_text.split("---", 2)[2].strip()
    client = create_client(model=os.environ.get("OPENAI_MODEL"))
    semaphore = asyncio.Semaphore(workers)
    selected = select_review_sample(master, sample_size)
    cache_dir = corpus_root / "quality/review-outputs"
    cache_dir.mkdir(parents=True, exist_ok=True)

    async def review(page: Path) -> dict:
        relative = page.relative_to(master).as_posix()
        source = plan[relative]
        claims = extract_claims(page)
        source_parts = []
        for record in sorted(records_by_doc[source["doc_id"]], key=lambda item: item["source_id"]):
            snapshot = json.loads((corpus_root / record["snapshot_path"]).read_text(encoding="utf-8"))
            source_parts.append(
                f"### [{record['source_id']}] {record.get('source_title', '')}\n"
                f"{_clean_snapshot(snapshot['markdown'])}"
            )
        prompt = prompt_text.format(
            source_content="\n\n".join(source_parts),
            wiki_content=page.read_text(encoding="utf-8"),
            claims="\n".join(f"{index}. {claim}" for index, claim in enumerate(claims, 1)),
        )
        input_sha256 = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        cache = cache_dir / f"{source['doc_id']}.json"

        def valid_result(value: object) -> bool:
            if not isinstance(value, dict) or not isinstance(value.get("checks"), list):
                return False
            expected_ids = list(range(1, len(claims) + 1))
            return [check.get("id") for check in value["checks"]] == expected_ids

        async with semaphore:
            cached = json.loads(cache.read_text(encoding="utf-8")) if cache.is_file() else None
            if (cached and cached.get("input_sha256") == input_sha256
                    and valid_result(cached.get("result"))):
                result = cached["result"]
            else:
                result = None
                usage = None
                for _ in range(2):
                    text, usage = await client.chat(
                        prompt, response_mime_type="application/json", temperature=0,
                    )
                    candidate = extract_json(text)
                    if valid_result(candidate):
                        result = candidate
                        break
                if not valid_result(result):
                    raise ValueError(f"invalid review output after retry for {relative}")
                cache.write_text(json.dumps({
                    "doc_id": source["doc_id"],
                    "model": getattr(client, "model", ""),
                    "input_sha256": input_sha256,
                    "claims": claims,
                    "result": result,
                    "prompt_tokens": getattr(usage, "prompt_tokens", 0) if usage else 0,
                    "completion_tokens": getattr(usage, "completion_tokens", 0) if usage else 0,
                }, ensure_ascii=False, indent=2), encoding="utf-8")
        if not valid_result(result):
            raise ValueError(f"invalid review output for {relative}")
        checks = result["checks"]
        return {
            "doc_id": source["doc_id"],
            "path": relative,
            "domain": source["domain"],
            "claims": claims,
            "checks": checks,
            "notes": result.get("notes", ""),
        }

    rows = await asyncio.gather(*(review(page) for page in selected))
    output = corpus_root / "quality/review-sample.jsonl"
    output.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    verdicts = Counter(
        check["verdict"] for row in rows for check in row["checks"]
    )
    decided = verdicts["supported"] + verdicts["unsupported"]
    support_rate = verdicts["supported"] / decided if decided else 0.0
    unsupported_numeric = [
        {"path": row["path"], "claim": row["claims"][check["id"] - 1]}
        for row in rows for check in row["checks"]
        if check["verdict"] == "unsupported"
        and any(char.isdigit() for char in row["claims"][check["id"] - 1])
    ]
    summary = {
        "passed": support_rate >= 0.95 and not unsupported_numeric,
        "sample_pages": len(rows),
        "claim_checks": sum(verdicts.values()),
        "verdicts": dict(verdicts),
        "support_rate_excluding_uncertain": round(support_rate, 6),
        "unsupported_numeric_claims": unsupported_numeric,
        "uncertain_requires_human_review": verdicts["uncertain"],
        "sample_paths": [row["path"] for row in rows],
    }
    (corpus_root / "quality/review-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    version_path = corpus_root / "VERSION.json"
    if summary["passed"] and version_path.is_file():
        version = json.loads(version_path.read_text(encoding="utf-8"))
        version.update({
            "quality_status": (
                "full-corpus-quality-gates-passed"
                if summary["sample_pages"] >= 50 else "pilot-quality-gates-passed"
            ),
            "review_sample_pages": summary["sample_pages"],
            "review_claim_checks": summary["claim_checks"],
            "review_support_rate": summary["support_rate_excluding_uncertain"],
            "review_summary_sha256": hashlib.sha256(
                (corpus_root / "quality/review-summary.json").read_bytes()
            ).hexdigest(),
        })
        version_path.write_text(
            json.dumps(version, ensure_ascii=False, indent=2), encoding="utf-8",
        )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus-root", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--sample-size", type=int, default=10)
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    summary = asyncio.run(review_corpus(
        args.corpus_root, args.sample_size, args.workers, args.plan,
    ))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    raise SystemExit(0 if summary["passed"] else 1)


if __name__ == "__main__":
    main()
