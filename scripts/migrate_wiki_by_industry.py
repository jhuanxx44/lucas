"""一次性迁移：将 wiki/companies/ 和 wiki/reports/ 按行业分子目录。"""

import os
import re
import shutil

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WIKI_DIR = os.path.join(PROJECT_ROOT, "wiki")
RAW_DIR = os.path.join(PROJECT_ROOT, "raw")


def build_company_industry_map() -> dict[str, str]:
    """从 raw/ 目录构建 {公司名: 行业} 映射。"""
    mapping = {}
    for industry in os.listdir(RAW_DIR):
        ind_path = os.path.join(RAW_DIR, industry)
        if not os.path.isdir(ind_path) or industry == "sources":
            continue
        for sub in os.listdir(ind_path):
            sub_path = os.path.join(ind_path, sub)
            if os.path.isdir(sub_path) and not os.path.isfile(os.path.join(sub_path, "meta.json")):
                mapping[sub] = industry
    return mapping


def extract_industry_from_sources(filepath: str) -> str | None:
    """从 wiki report 的 frontmatter sources 字段提取行业。"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        return None
    m = re.search(r"raw/([^/]+)/", content)
    return m.group(1) if m else None


def migrate_companies(mapping: dict[str, str]):
    companies_dir = os.path.join(WIKI_DIR, "companies")
    if not os.path.isdir(companies_dir):
        return

    for fname in os.listdir(companies_dir):
        if not fname.endswith(".md"):
            continue
        fpath = os.path.join(companies_dir, fname)
        if not os.path.isfile(fpath):
            continue

        name_no_ext = fname.replace(".md", "")
        company_name = re.sub(r"^\d+-", "", name_no_ext)
        industry = mapping.get(company_name, "未分类")

        dest_dir = os.path.join(companies_dir, industry)
        os.makedirs(dest_dir, exist_ok=True)
        dest = os.path.join(dest_dir, fname)
        print(f"  companies/{fname} -> companies/{industry}/{fname}")
        shutil.move(fpath, dest)


def migrate_reports():
    reports_dir = os.path.join(WIKI_DIR, "reports")
    if not os.path.isdir(reports_dir):
        return

    for fname in os.listdir(reports_dir):
        if not fname.endswith(".md"):
            continue
        fpath = os.path.join(reports_dir, fname)
        if not os.path.isfile(fpath):
            continue

        industry = extract_industry_from_sources(fpath) or "未分类"
        dest_dir = os.path.join(reports_dir, industry)
        os.makedirs(dest_dir, exist_ok=True)
        dest = os.path.join(dest_dir, fname)
        print(f"  reports/{fname} -> reports/{industry}/{fname}")
        shutil.move(fpath, dest)
def rewrite_index(mapping: dict[str, str]):
    """重写 wiki/index.md，按新目录结构生成索引。"""
    companies_dir = os.path.join(WIKI_DIR, "companies")
    reports_dir = os.path.join(WIKI_DIR, "reports")

    lines = ["# Lucas A股股市 Wiki 索引\n"]

    # 公司档案 — 按行业
    for industry in sorted(os.listdir(companies_dir)):
        ind_path = os.path.join(companies_dir, industry)
        if not os.path.isdir(ind_path):
            continue
        lines.append(f"\n## 公司档案 · {industry}")
        for fname in sorted(os.listdir(ind_path)):
            if not fname.endswith(".md"):
                continue
            name = fname.replace(".md", "")
            lines.append(f"- [{name}](companies/{industry}/{fname})")

    # 行业概览
    industries_dir = os.path.join(WIKI_DIR, "industries")
    if os.path.isdir(industries_dir):
        ind_files = sorted(f for f in os.listdir(industries_dir) if f.endswith(".md"))
        if ind_files:
            lines.append("\n## 行业概览")
            for fname in ind_files:
                name = fname.replace(".md", "")
                lines.append(f"- [{name}](industries/{fname})")

    # 概念/主题
    concepts_dir = os.path.join(WIKI_DIR, "concepts")
    if os.path.isdir(concepts_dir):
        concept_files = sorted(f for f in os.listdir(concepts_dir) if f.endswith(".md"))
        if concept_files:
            lines.append("\n## 概念/主题")
            for fname in concept_files:
                name = fname.replace(".md", "")
                lines.append(f"- [{name}](concepts/{fname})")

    # 术语表
    if os.path.isfile(os.path.join(WIKI_DIR, "glossary.md")):
        lines.append("\n## 术语表")
        lines.append("- [A股术语表](glossary.md)")

    # 分析报告 — 按行业
    for industry in sorted(os.listdir(reports_dir)):
        ind_path = os.path.join(reports_dir, industry)
        if not os.path.isdir(ind_path):
            continue
        lines.append(f"\n## 分析报告 · {industry}")
        for fname in sorted(os.listdir(ind_path)):
            if not fname.endswith(".md"):
                continue
            name = fname.split("_", 1)[1].replace(".md", "") if "_" in fname else fname.replace(".md", "")
            lines.append(f"- [{name}](reports/{industry}/{fname})")

    index_path = os.path.join(WIKI_DIR, "index.md")
    with open(index_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"  重写 index.md ({len(lines)} 行)")


if __name__ == "__main__":
    print("构建公司-行业映射...")
    mapping = build_company_industry_map()
    for company, industry in sorted(mapping.items()):
        print(f"  {company} -> {industry}")

    print("\n迁移 companies/...")
    migrate_companies(mapping)

    print("\n迁移 reports/...")
    migrate_reports()

    print("\n重写 index.md...")
    rewrite_index(mapping)

    print("\n完成！")
