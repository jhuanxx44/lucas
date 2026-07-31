#!/usr/bin/env python3
"""将冻结抓取快照经 LLM 整理为可追溯 Wiki 页面。"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from utils.json_extract import extract_json
from utils.llm_client import create_client
from scripts.wiki_corpus_common import load_jsonl, validate_source_plan, validate_wiki_page


DEFAULT_CORPUS = ROOT / "evals/corpora/wiki-scale-v1"
PROMPT_PATH = ROOT / "prompts/evals/wiki-corpus-compile.md"
MAX_SOURCE_CHARS = 50_000


def _load_prompt() -> str:
    text = PROMPT_PATH.read_text(encoding="utf-8")
    if text.startswith("---\n"):
        text = text.split("---", 2)[2]
    return text.strip()


def _clean_snapshot(markdown: str) -> str:
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", markdown)
    for _ in range(5):
        cleaned = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
        if cleaned == text:
            break
        text = cleaned
    text = re.sub(r"\[(?:编辑|編輯)\]", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    for heading in ("参考文献", "參考文獻", "外部链接", "外部連結"):
        text = re.split(rf"\n##+\s*{heading}\s*\n", text, maxsplit=1)[0]
    return text.strip()[:MAX_SOURCE_CHARS]


def _render_page(source: dict, records: list[dict], llm_result: dict,
                 as_of: str) -> str:
    title = Path(source["target_path"]).stem
    frontmatter = {
        "title": title,
        "type": source["page_type"],
        "industry": source["domain"],
        "as_of": as_of,
        "summary": llm_result["summary"].strip(),
        "source_ids": [record["source_id"] for record in records],
    }
    body = llm_result["body"].strip()
    lines = [
        "---",
        yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False).strip(),
        "---",
        "",
        f"# {title}",
        "",
        body,
        "",
        "## 来源",
        "",
    ]
    for record in records:
        source_title = record.get("source_title") or record["requested_url"]
        retrieved = record["retrieved_at"][:10]
        lines.append(
            f"- [{record['source_id']}] {source_title} — "
            f"{record['source_url']}（抓取日期：{retrieved}）"
        )
    return "\n".join(lines).rstrip() + "\n"


def _ground_single_source_numbers(body: str, source_ids: list[str]) -> str:
    """单来源页中，给 LLM 拆到表格/列表独立行的数字补上唯一可选来源。"""
    if len(source_ids) != 1:
        return body
    marker = f"[{source_ids[0]}]"
    lines = []
    for line in body.splitlines():
        stripped = line.strip()
        if (any(character.isdigit() for character in line)
                and marker not in line
                and stripped
                and not stripped.startswith("#")
                and not re.fullmatch(r"\|?\s*[:|\- ]+\|?", stripped)):
            line = f"{line.rstrip()} {marker}"
        lines.append(line)
    return "\n".join(lines)


async def _compile_one(client, prompt_template: str, source: dict,
                       records: list[dict], corpus_root: Path,
                       force: bool) -> dict:
    destination = corpus_root / "master/wiki" / source["target_path"]
    if destination.is_file() and not force:
        return {"doc_id": source["doc_id"], "status": "reused", "path": source["target_path"]}

    source_parts = []
    for record in records:
        snapshot = corpus_root / record["snapshot_path"]
        data = json.loads(snapshot.read_text(encoding="utf-8"))
        cleaned = _clean_snapshot(data["markdown"])
        source_parts.append(
            f"### [{record['source_id']}] {record.get('source_title', '')}\n"
            f"URL: {record['source_url']}\n\n{cleaned}"
        )
    prompt = prompt_template.format(
        title=Path(source["target_path"]).stem,
        page_type=source["page_type"],
        domain=source["domain"],
        reason=source["reason"],
        source_content="\n\n".join(source_parts),
    )
    try:
        cache = corpus_root / "quality/llm-outputs" / f"{source['doc_id']}.json"
        usage = None
        if cache.is_file() and not force:
            result = json.loads(cache.read_text(encoding="utf-8"))["result"]
        else:
            text, usage = await client.generate_text(
                prompt, response_mime_type="application/json", temperature=0,
            )
            result = extract_json(text)
        if not isinstance(result, dict):
            raise ValueError("LLM output is not a JSON object")
        summary = result.get("summary")
        body = result.get("body")
        if not isinstance(summary, str) or not summary.strip():
            raise ValueError("LLM returned an empty summary")
        if not isinstance(body, str) or len(body.strip()) < 300:
            raise ValueError("LLM returned an empty or too-short body")

        raw_result = {"summary": summary, "body": body}
        source_ids = [record["source_id"] for record in records]
        result = {
            "summary": summary,
            "body": _ground_single_source_numbers(body, source_ids),
        }
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({
            "doc_id": source["doc_id"],
            "model": getattr(client, "model", os.environ.get("DEEPSEEK_MODEL", "")),
            "source_hashes": [record["content_sha256"] for record in records],
            "raw_result": raw_result,
            "result": result,
        }, ensure_ascii=False, indent=2), encoding="utf-8")

        page = _render_page(source, records, result, date.today().isoformat())
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(".md.part")
        temporary.write_text(page, encoding="utf-8")
        errors = validate_wiki_page(
            temporary, {record["source_id"] for record in records},
        )
        if errors:
            temporary.unlink(missing_ok=True)
            raise ValueError("; ".join(errors[:10]))
        temporary.replace(destination)
        return {
            "doc_id": source["doc_id"],
            "status": "ok",
            "path": source["target_path"],
            "chars": len(page),
            "model": getattr(client, "model", os.environ.get("DEEPSEEK_MODEL", "")),
            "prompt_tokens": getattr(usage, "prompt_tokens", 0) if usage else 0,
            "completion_tokens": getattr(usage, "completion_tokens", 0) if usage else 0,
        }
    except Exception as exc:
        return {
            "doc_id": source["doc_id"],
            "status": "compile_failed",
            "path": source["target_path"],
            "error": str(exc)[:2000],
        }


async def compile_corpus(plan_path: Path, corpus_root: Path, workers: int,
                         limit: int | None = None,
                         doc_ids: set[str] | None = None,
                         force: bool = False) -> list[dict]:
    sources = load_jsonl(plan_path)
    errors = validate_source_plan(sources)
    if errors:
        raise ValueError("invalid source plan:\n" + "\n".join(errors))
    if doc_ids:
        sources = [source for source in sources if source["doc_id"] in doc_ids]
        missing = doc_ids - {source["doc_id"] for source in sources}
        if missing:
            raise ValueError(f"unknown doc ids: {sorted(missing)}")
    if limit is not None:
        sources = sources[:limit]

    catalog = load_jsonl(corpus_root / "sources/catalog.jsonl")
    records_by_doc: dict[str, list[dict]] = {}
    for record in catalog:
        if record.get("status") == "ok":
            records_by_doc.setdefault(record["doc_id"], []).append(record)
    ready = []
    results = []
    for source in sources:
        records = sorted(records_by_doc.get(source["doc_id"], []), key=lambda r: r["source_id"])
        if len(records) != len(source["urls"]):
            results.append({
                "doc_id": source["doc_id"], "status": "missing_snapshot",
                "path": source["target_path"],
            })
        else:
            ready.append((source, records))

    client = create_client(model=os.environ.get("DEEPSEEK_MODEL"))
    prompt = _load_prompt()
    semaphore = asyncio.Semaphore(workers)

    async def run(source, records):
        async with semaphore:
            result = await _compile_one(client, prompt, source, records, corpus_root, force)
            print(f"[{result['status']}] {source['doc_id']}", flush=True)
            return result

    results.extend(await asyncio.gather(*(run(source, records) for source, records in ready)))
    results.sort(key=lambda value: value["doc_id"])
    output = corpus_root / "quality/compile-results.jsonl"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "".join(json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n" for result in results),
        encoding="utf-8",
    )
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, default=DEFAULT_CORPUS / "source-plan.jsonl")
    parser.add_argument("--corpus-root", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--doc-id", action="append", default=[])
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.workers < 1 or args.workers > 4:
        parser.error("--workers must be between 1 and 4")
    results = asyncio.run(compile_corpus(
        args.plan, args.corpus_root, args.workers, args.limit,
        set(args.doc_id) or None, args.force,
    ))
    counts: dict[str, int] = {}
    for result in results:
        counts[result["status"]] = counts.get(result["status"], 0) + 1
    print(json.dumps(counts, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
