import pytest
from server.services.wiki_parser import parse_wiki_index, parse_wiki_page, search_wiki


def test_parse_wiki_index_extracts_sections(tmp_path):
    index_md = tmp_path / "index.md"
    index_md.write_text("""# Lucas A股股市 Wiki 索引

## 公司档案
- [300750-宁德时代](companies/300750-宁德时代.md) — 动力电池全球龙头
- [002463-沪电股份](companies/002463-沪电股份.md)

## 行业概览
- [PCB](industries/PCB.md)

## 概念/主题
（暂无，等待编译）

## 分析报告
- [研究下东山精密](reports/2026-04-20_研究下东山精密.md)
""", encoding="utf-8")
    result = parse_wiki_index(str(tmp_path))
    assert len(result["sections"]) >= 3
    company_section = next(s for s in result["sections"] if s["title"] == "公司档案")
    assert len(company_section["items"]) == 2
    assert company_section["items"][0]["name"] == "300750-宁德时代"
    assert company_section["items"][0]["path"] == "companies/300750-宁德时代.md"


def test_parse_wiki_page_with_frontmatter(tmp_path):
    page = tmp_path / "test.md"
    page.write_text("""---
title: 宁德时代（300750）
type: company
tags: [动力电池, 储能]
confidence: high
updated: 2026-04-17
sources:
  - raw/financial-reports/xxx.md
---

# 宁德时代

## 概述
全球动力电池龙头。

## 相关链接
[[PCB]] [[AI算力]]
""", encoding="utf-8")
    result = parse_wiki_page(str(page))
    assert result["frontmatter"]["title"] == "宁德时代（300750）"
    assert result["frontmatter"]["type"] == "company"
    assert result["frontmatter"]["confidence"] == "high"
    assert "全球动力电池龙头" in result["content"]
    assert "PCB" in result["wiki_links"]
    assert "AI算力" in result["wiki_links"]


def test_search_wiki_matches_filename_and_content(tmp_path):
    companies = tmp_path / "companies"
    companies.mkdir()
    (companies / "宁德时代.md").write_text("---\ntitle: 宁德时代\n---\n动力电池龙头", encoding="utf-8")
    (companies / "沪电.md").write_text("---\ntitle: 沪电股份\n---\nPCB行业", encoding="utf-8")
    results = search_wiki(str(tmp_path), "电池")
    assert len(results) >= 1
    assert any("宁德" in r["name"] for r in results)
