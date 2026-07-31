#!/usr/bin/env python3
"""批量策展真实链接候选，并按领域配额生成最终 500 篇 source plan。"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.discover_wiki_sources import DOMAIN_TARGETS, group_for_domain, title_key
from scripts.wiki_corpus_common import load_jsonl, validate_source_plan
from utils.json_extract import extract_json
from utils.llm_client import create_client


DEFAULT_CORPUS = ROOT / "evals/corpora/wiki-scale-v1"
PROMPT_PATH = ROOT / "prompts/evals/wiki-source-select.md"


async def classify_candidates(corpus_root: Path, candidates_path: Path,
                              batch_size: int, workers: int) -> list[dict]:
    pilot = load_jsonl(corpus_root / "source-plan.jsonl")
    candidates = load_jsonl(candidates_path)[len(pilot):]
    prompt_template = PROMPT_PATH.read_text(encoding="utf-8")
    if prompt_template.startswith("---\n"):
        prompt_template = prompt_template.split("---", 2)[2].strip()
    client = create_client(model=os.environ.get("DEEPSEEK_MODEL"))
    cache_dir = corpus_root / "quality/source-selection"
    cache_dir.mkdir(parents=True, exist_ok=True)
    semaphore = asyncio.Semaphore(workers)

    batches = [candidates[index:index + batch_size] for index in range(0, len(candidates), batch_size)]

    async def classify(batch_index: int, batch: list[dict]) -> list[dict]:
        inputs = [
            {
                "id": index,
                "title": Path(candidate["target_path"]).stem,
                "suggested_domain": candidate["domain"],
                "url": candidate["urls"][0],
            }
            for index, candidate in enumerate(batch, 1)
        ]
        prompt = prompt_template.format(candidates=json.dumps(inputs, ensure_ascii=False, indent=2))
        digest = hashlib.sha256(prompt.encode()).hexdigest()
        cache = cache_dir / f"batch-{batch_index:03d}.json"
        async with semaphore:
            cached = json.loads(cache.read_text(encoding="utf-8")) if cache.is_file() else None
            if cached and cached.get("input_sha256") == digest:
                result = cached["result"]
            else:
                text, usage = await client.generate_text(
                    prompt, response_mime_type="application/json", temperature=0,
                )
                result = extract_json(text)
                cache.write_text(json.dumps({
                    "input_sha256": digest,
                    "model": getattr(client, "model", ""),
                    "result": result,
                    "prompt_tokens": getattr(usage, "prompt_tokens", 0) if usage else 0,
                    "completion_tokens": getattr(usage, "completion_tokens", 0) if usage else 0,
                }, ensure_ascii=False, indent=2), encoding="utf-8")
        if not isinstance(result, dict) or not isinstance(result.get("items"), list):
            raise ValueError(f"batch {batch_index}: invalid LLM result")
        items = result["items"]
        if [item.get("id") for item in items] != list(range(1, len(batch) + 1)):
            raise ValueError(f"batch {batch_index}: ids do not match inputs")
        output = []
        for candidate, item in zip(batch, items):
            if item.get("domain") not in DOMAIN_TARGETS:
                raise ValueError(f"batch {batch_index}: invalid domain {item.get('domain')}")
            if item.get("page_type") not in ("company", "industry", "concept"):
                raise ValueError(f"batch {batch_index}: invalid page_type")
            output.append({
                "doc_id": candidate["doc_id"],
                "title": Path(candidate["target_path"]).stem,
                "url": candidate["urls"][0],
                "suggested_domain": candidate["domain"],
                "seed_doc_ids": candidate.get("discovery", {}).get("seed_doc_ids", []),
                "keep": item.get("keep") is True,
                "domain": item["domain"],
                "page_type": item["page_type"],
                "reason": str(item.get("reason", "")),
            })
        print(f"[classified] batch {batch_index}/{len(batches)}", flush=True)
        return output

    classified_batches = await asyncio.gather(*(
        classify(index, batch) for index, batch in enumerate(batches, 1)
    ))
    classified = [item for batch in classified_batches for item in batch]
    output = corpus_root / "quality/candidate-classifications.jsonl"
    output.write_text(
        "".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in classified),
        encoding="utf-8",
    )
    return classified


def build_final_plan(corpus_root: Path, classified: list[dict], output_path: Path) -> list[dict]:
    pilot = load_jsonl(corpus_root / "source-plan.jsonl")
    group_targets = {"target": 150, "near": 200, "far": 150}
    current = Counter(group_for_domain(entry["domain"]) for entry in pilot)
    used_urls = {url for entry in pilot for url in entry["urls"]}
    used_titles = {title_key(Path(entry["target_path"]).stem) for entry in pilot}
    by_domain: dict[str, list[dict]] = defaultdict(list)
    for item in classified:
        if item["keep"]:
            by_domain[item["domain"]].append(item)
    for items in by_domain.values():
        items.sort(key=lambda item: (
            -len(item["seed_doc_ids"]),
            hashlib.sha256(f"selected:{item['domain']}:{item['title']}".encode()).hexdigest(),
        ))

    additions = []
    shortages = {}
    for group, target in group_targets.items():
        needed = target - current[group]
        domains = sorted(
            domain for domain in DOMAIN_TARGETS if group_for_domain(domain) == group
        )
        chosen = 0
        offsets = Counter()
        while chosen < needed:
            progressed = False
            for domain in domains:
                items = by_domain[domain]
                while offsets[domain] < len(items):
                    item = items[offsets[domain]]
                    offsets[domain] += 1
                    key = title_key(item["title"])
                    if item["url"] in used_urls or key in used_titles:
                        continue
                    safe_title = item["title"].replace("/", "／")
                    prefix = "companies" if item["page_type"] == "company" else "concepts"
                    additions.append({
                        "doc_id": item["doc_id"],
                        "target_path": f"{prefix}/{domain}/{safe_title}.md",
                        "domain": domain,
                        "page_type": item["page_type"],
                        "source_tier": 2,
                        "urls": [item["url"]],
                        "reason": item["reason"],
                        "discovery": {
                            "method": "pilot-body-link+llm-curation",
                            "seed_doc_ids": item["seed_doc_ids"],
                        },
                    })
                    used_urls.add(item["url"])
                    used_titles.add(key)
                    chosen += 1
                    progressed = True
                    break
                if chosen == needed:
                    break
            if not progressed:
                break
        if chosen != needed:
            shortages[group] = {"needed": needed, "selected": chosen}
    if shortages:
        raise ValueError("insufficient curated candidates: " + json.dumps(shortages, ensure_ascii=False))
    plan = pilot + additions
    errors = validate_source_plan(plan)
    if errors:
        raise ValueError("final source plan invalid:\n" + "\n".join(errors[:20]))
    output_path.write_text(
        "".join(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n" for entry in plan),
        encoding="utf-8",
    )
    return plan


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus-root", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CORPUS / "discovered-candidates.jsonl")
    parser.add_argument("--output", type=Path, default=DEFAULT_CORPUS / "source-plan-500.jsonl")
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    classified = asyncio.run(classify_candidates(
        args.corpus_root, args.candidates, args.batch_size, args.workers,
    ))
    plan = build_final_plan(args.corpus_root, classified, args.output)
    print(json.dumps({
        "classified": len(classified),
        "kept": sum(item["keep"] for item in classified),
        "final_documents": len(plan),
        "domains": Counter(entry["domain"] for entry in plan),
    }, ensure_ascii=False, default=dict))


if __name__ == "__main__":
    main()
