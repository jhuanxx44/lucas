#!/usr/bin/env python3
"""从已抓取试点页面的正文内链发现真实 Wikipedia 扩库来源。"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.wiki_corpus_common import load_jsonl, validate_source_plan


DEFAULT_CORPUS = ROOT / "evals/corpora/wiki-scale-v1"
GROUPS = {
    "target": {"半导体", "光通信", "通信"},
    "near": {"人工智能", "云计算", "互联网", "汽车", "新能源", "消费电子", "软件服务"},
}
DOMAIN_TARGETS = {
    "半导体": 95, "光通信": 50, "通信": 5,
    "人工智能": 25, "云计算": 30, "互联网": 35, "汽车": 35,
    "新能源": 20, "消费电子": 25, "软件服务": 30,
    "食品饮料": 20, "餐饮": 30, "体育用品": 25,
    "文化": 25, "自然": 20, "体育": 30,
}
_LINK_RE = re.compile(
    r"\[[^\]]*\]\((https://zh\.wikipedia\.org/wiki/[^)\s]+(?:\([^)]*\))?)"
    r"(?:\s+\"[^\"]*\")?\)"
)
_BAD_PREFIXES = (
    "File:", "Category:", "Special:", "Help:", "Wikipedia:", "Template:",
    "Portal:", "Talk:", "User:", "Draft:", "Module:", "MediaWiki:",
    "文件:", "分類:", "分类:", "特殊:", "維基百科:", "维基百科:", "模板:",
)
_BAD_TITLES = {
    "中华人民共和国", "美国", "中国", "日本", "欧洲", "公司", "企业", "互联网",
    "首页", "主页", "英语", "英語", "中文", "汉语", "漢語", "产业", "產業",
    "营业额", "營業額", "利润", "利潤", "资产", "資產", "上市公司",
    "股票代号", "股票代號", "股东权益", "股東權益", "组织创始人", "組織創始人",
    "国际标准书号", "数字对象标识符", "互联网档案馆", "網際網路檔案館",
}
_TITLE_T2S = str.maketrans({
    "臺": "台", "灣": "湾", "積": "积", "體": "体", "電": "电",
    "製": "制", "廠": "厂", "訊": "讯", "華": "华", "國": "国",
    "門": "门", "業": "业", "產": "产", "聯": "联", "發": "发",
    "軟": "软", "網": "网", "際": "际", "導": "导", "學": "学",
    "資": "资", "雲": "云", "計": "计", "據": "据", "長": "长",
    "東": "东", "馬": "马", "車": "车", "萬": "万", "與": "与",
    "為": "为", "團": "团", "組": "组", "織": "织", "創": "创",
})


def group_for_domain(domain: str) -> str:
    if domain in GROUPS["target"]:
        return "target"
    if domain in GROUPS["near"]:
        return "near"
    return "far"


def canonical_wikipedia_link(url: str) -> tuple[str, str] | None:
    parsed = urlparse(url)
    if parsed.netloc != "zh.wikipedia.org" or not parsed.path.startswith("/wiki/"):
        return None
    title = unquote(parsed.path[len("/wiki/"):]).replace("_", " ").strip()
    if (not title or len(title) > 50 or ":" in title
            or title.count("(") != title.count(")")
            or title.startswith(_BAD_PREFIXES) or title in _BAD_TITLES
            or title.startswith(("List of ", "列表", "消歧义"))):
        return None
    canonical = "https://zh.wikipedia.org/wiki/" + quote(title.replace(" ", "_"), safe="()_-.")
    return title, canonical


def title_key(title: str) -> str:
    return unicodedata.normalize("NFKC", title).translate(_TITLE_T2S).replace(" ", "").casefold()


def _body_before_references(markdown: str) -> str:
    for heading in ("参考文献", "參考文獻", "外部链接", "外部連結"):
        markdown = re.split(rf"\n##+\s*{heading}\s*\n", markdown, maxsplit=1)[0]
    # Firecrawl 会把 Wikipedia infobox 和导航框转成 Markdown 表格；这些字段链接
    # （营业额、股东权益等）不是正文主题，不能作为扩库候选。
    return "\n".join(
        line for line in markdown.splitlines()
        if not line.lstrip().startswith("|")
    )


def _page_type(title: str) -> str:
    company_terms = ("公司", "集团", "集團", "股份", "科技", "电子", "電信", "银行", "汽車")
    return "company" if title.endswith(company_terms) else "concept"


def discover(corpus_root: Path, output_path: Path, multiplier: int = 1) -> list[dict]:
    pilot = load_jsonl(corpus_root / "source-plan.jsonl")
    catalog = load_jsonl(corpus_root / "sources/catalog.jsonl")
    source_by_doc = {entry["doc_id"]: entry for entry in pilot}
    existing_urls = set()
    existing_titles = {title_key(Path(entry["target_path"]).stem) for entry in pilot}
    for entry in pilot:
        for url in entry["urls"]:
            parsed = canonical_wikipedia_link(url)
            if parsed:
                existing_titles.add(title_key(parsed[0]))
                existing_urls.add(parsed[1])

    candidates: dict[str, dict[str, dict]] = defaultdict(dict)
    for record in catalog:
        if record.get("status") != "ok" or record["source_id"] != "S1":
            continue
        seed = source_by_doc[record["doc_id"]]
        domain = seed["domain"]
        snapshot = json.loads((corpus_root / record["snapshot_path"]).read_text(encoding="utf-8"))
        body = _body_before_references(snapshot["markdown"])
        for raw_url in _LINK_RE.findall(body):
            parsed = canonical_wikipedia_link(raw_url)
            if parsed is None:
                continue
            title, url = parsed
            if url in existing_urls or title_key(title) in existing_titles:
                continue
            candidate = candidates[domain].setdefault(title, {
                "title": title,
                "url": url,
                "domains": Counter(),
                "seed_docs": set(),
            })
            candidate["domains"][seed["domain"]] += 1
            candidate["seed_docs"].add(seed["doc_id"])

    additions = []
    selected_urls = set(existing_urls)
    selected_titles = set(existing_titles)
    current_counts = Counter(entry["domain"] for entry in pilot)
    for domain, target_count in DOMAIN_TARGETS.items():
        needed = (target_count - current_counts[domain]) * multiplier
        group = group_for_domain(domain)
        ranked = sorted(
            candidates[domain].values(),
            key=lambda value: (
                -len(value["seed_docs"]),
                hashlib.sha256(f"wiki-scale-v1:{group}:{value['title']}".encode()).hexdigest(),
            ),
        )
        chosen = 0
        for candidate in ranked:
            if chosen == needed:
                break
            candidate_key = title_key(candidate["title"])
            if candidate["url"] in selected_urls or candidate_key in selected_titles:
                continue
            page_type = _page_type(candidate["title"])
            safe_title = candidate["title"].replace("/", "／")
            target_path = (
                f"companies/{domain}/{safe_title}.md" if page_type == "company"
                else f"concepts/{domain}/{safe_title}.md"
            )
            digest = hashlib.sha1(candidate["url"].encode()).hexdigest()[:12]
            additions.append({
                "doc_id": f"wp-{digest}",
                "target_path": target_path,
                "domain": domain,
                "page_type": page_type,
                "source_tier": 2,
                "urls": [candidate["url"]],
                "reason": f"由 {group} 领域试点页面正文内链发现，扩展真实知识覆盖",
                "discovery": {
                    "method": "pilot-body-link",
                    "group": group,
                    "seed_doc_ids": sorted(candidate["seed_docs"]),
                },
            })
            selected_urls.add(candidate["url"])
            selected_titles.add(candidate_key)
            chosen += 1
        if chosen != needed:
            raise ValueError(f"not enough {domain} candidates: need {needed}, found {chosen}")

    full_plan = pilot + additions
    errors = validate_source_plan(full_plan)
    if errors:
        raise ValueError("generated plan is invalid:\n" + "\n".join(errors[:20]))
    output_path.write_text(
        "".join(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n" for entry in full_plan),
        encoding="utf-8",
    )
    return full_plan


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus-root", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--output", type=Path, default=DEFAULT_CORPUS / "source-plan-500.jsonl")
    parser.add_argument("--multiplier", type=int, default=1)
    args = parser.parse_args()
    if args.multiplier < 1:
        parser.error("--multiplier must be positive")
    plan = discover(args.corpus_root, args.output, args.multiplier)
    groups = Counter(group_for_domain(entry["domain"]) for entry in plan)
    domains = Counter(entry["domain"] for entry in plan)
    print(json.dumps({"documents": len(plan), "groups": groups, "domains": domains}, ensure_ascii=False, default=dict))


if __name__ == "__main__":
    main()
