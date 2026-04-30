"""
一次性迁移脚本：将 raw/reports/{date}/{researcher}_{slug}.md 迁移到新结构
raw/{行业}/{公司}/{date}_{slug}/ + meta.json

同时：
- raw/financial-reports/ → raw/sources/
- 删除空目录（research/macro/news/industry/strategy）
- 更新 wiki/reports/ 中的 sources 路径
"""
import glob
import json
import os
import re
import shutil
import yaml

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
RAW_DIR = os.path.join(PROJECT_ROOT, "raw")
WIKI_DIR = os.path.join(PROJECT_ROOT, "wiki")

# 手动映射：旧 slug → (行业, 公司列表)
# 公司列表为空表示行业级报告
SLUG_MAP = {
    "宁德时代走势分析": ("新能源", ["宁德时代"]),
    "胜宏科技vs沪电股份对比分析": ("电子", ["胜宏科技"]),
    "东山精密深度分析": ("电子", ["东山精密"]),
    "和东山精密三者一起对比下": ("电子", ["东山精密"]),
    "PCB超级周期核心受益分析": ("电子", []),
    "研究天孚通信基本面": ("电子", ["天孚通信"]),
    "横向对比永鼎股份，亨通光电，还有光库科技": ("电子", ["永鼎股份"]),
    "如何看待英维克26年一季报": ("电子", ["英维克"]),
    "调研下多氟多_天际股份": ("化工", ["多氟多"]),
    "对比多氟多，对比下天赐材料": ("化工", ["多氟多"]),
    "天通股份软磁材料龙头地位与产业链分析": ("电子", ["天通股份"]),
    "立讯精密苹果产业链依赖与汽车业务增长潜力分析": ("电子", ["立讯精密"]),
    "光芯片与光模块产业链区别及优质标的筛选": ("电子", []),
}
# PLACEHOLDER_FOR_APPEND


def parse_frontmatter(content: str) -> dict:
    if not content.startswith("---\n"):
        return {}
    end = content.find("\n---\n", 4)
    if end == -1:
        return {}
    try:
        return yaml.safe_load(content[4:end]) or {}
    except yaml.YAMLError:
        return {}


def extract_slug(filename: str) -> str:
    """从 'researcher_slug.md' 中提取 slug"""
    name = os.path.splitext(filename)[0]
    parts = name.split("_", 1)
    return parts[1] if len(parts) > 1 else name


def extract_researcher_id(filename: str) -> str:
    """从 'researcher_slug.md' 中提取 researcher id"""
    name = os.path.splitext(filename)[0]
    return name.split("_", 1)[0]


def make_slug(text: str) -> str:
    slug = text.replace(" ", "_").replace("/", "_").replace("?", "").replace("？", "")
    return slug[:40]


def migrate_reports():
    old_reports_dir = os.path.join(RAW_DIR, "reports")
    if not os.path.isdir(old_reports_dir):
        print("raw/reports/ 不存在，跳过")
        return

    # 按 (date, slug) 分组旧报告
    groups: dict[tuple[str, str], list[str]] = {}
    for date_dir in sorted(os.listdir(old_reports_dir)):
        date_path = os.path.join(old_reports_dir, date_dir)
        if not os.path.isdir(date_path):
            continue
        for filename in sorted(os.listdir(date_path)):
            if not filename.endswith(".md"):
                continue
            slug = extract_slug(filename)
            key = (date_dir, slug)
            groups.setdefault(key, []).append(os.path.join(date_path, filename))

    path_mapping = {}  # old_rel → new_rel

    for (report_date, slug), files in sorted(groups.items()):
        industry, companies = SLUG_MAP.get(slug, ("未分类", []))
        dir_slug = make_slug(slug)

        if companies:
            new_dir = os.path.join(RAW_DIR, industry, companies[0], f"{report_date}_{dir_slug}")
        else:
            new_dir = os.path.join(RAW_DIR, industry, f"{report_date}_{dir_slug}")

        os.makedirs(new_dir, exist_ok=True)

        researchers = []
        all_urls = []
        question = slug
        for old_path in files:
            filename = os.path.basename(old_path)
            researcher_id = extract_researcher_id(filename)

            with open(old_path, "r", encoding="utf-8") as f:
                content = f.read()
            fm = parse_frontmatter(content)
            if fm.get("question"):
                question = fm["question"]

            new_path = os.path.join(new_dir, f"{researcher_id}.md")
            shutil.copy2(old_path, new_path)

            old_rel = os.path.relpath(old_path, PROJECT_ROOT)
            new_rel = os.path.relpath(new_path, PROJECT_ROOT)
            path_mapping[old_rel] = new_rel

            researchers.append({
                "id": researcher_id,
                "name": fm.get("researcher", researcher_id),
                "model": fm.get("model", "unknown"),
            })
            print(f"  {old_rel} → {new_rel}")

        meta = {
            "question": question,
            "title": slug,
            "date": report_date,
            "industry": industry,
            "companies": companies,
            "researchers": researchers,
            "source_urls": all_urls,
        }
        meta_path = os.path.join(new_dir, "meta.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        print(f"  写入 {os.path.relpath(meta_path, PROJECT_ROOT)}")

    return path_mapping


def migrate_financial_reports():
    old_dir = os.path.join(RAW_DIR, "financial-reports")
    new_dir = os.path.join(RAW_DIR, "sources")
    if not os.path.isdir(old_dir):
        print("raw/financial-reports/ 不存在，跳过")
        return

    os.makedirs(new_dir, exist_ok=True)
    for filename in os.listdir(old_dir):
        old_path = os.path.join(old_dir, filename)
        new_path = os.path.join(new_dir, filename)
        if os.path.isfile(old_path):
            shutil.copy2(old_path, new_path)
            print(f"  {os.path.relpath(old_path, PROJECT_ROOT)} → {os.path.relpath(new_path, PROJECT_ROOT)}")


def update_wiki_sources(path_mapping: dict):
    """更新 wiki/reports/ 中 frontmatter 的 sources 路径"""
    wiki_reports = os.path.join(WIKI_DIR, "reports")
    if not os.path.isdir(wiki_reports):
        return

    for filename in os.listdir(wiki_reports):
        if not filename.endswith(".md"):
            continue
        filepath = os.path.join(wiki_reports, filename)
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        updated = content
        for old_rel, new_rel in path_mapping.items():
            updated = updated.replace(old_rel, new_rel)

        # 也更新 financial-reports → sources
        updated = updated.replace("raw/financial-reports/", "raw/sources/")

        if updated != content:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(updated)
            print(f"  更新 wiki/reports/{filename}")


def update_wiki_company_sources():
    """更新 wiki/companies/ 中 frontmatter 的 sources 路径"""
    companies_dir = os.path.join(WIKI_DIR, "companies")
    if not os.path.isdir(companies_dir):
        return

    for filename in os.listdir(companies_dir):
        if not filename.endswith(".md"):
            continue
        filepath = os.path.join(companies_dir, filename)
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        updated = content.replace("raw/financial-reports/", "raw/sources/")
        if updated != content:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(updated)
            print(f"  更新 wiki/companies/{filename}")


def cleanup_old_dirs():
    """删除旧的空目录和已迁移的目录"""
    empty_dirs = ["research", "macro", "news", "industry", "strategy"]
    for d in empty_dirs:
        path = os.path.join(RAW_DIR, d)
        if os.path.isdir(path):
            shutil.rmtree(path)
            print(f"  删除 raw/{d}/")

    # 删除旧 reports 和 financial-reports
    for d in ["reports", "financial-reports"]:
        path = os.path.join(RAW_DIR, d)
        if os.path.isdir(path):
            shutil.rmtree(path)
            print(f"  删除 raw/{d}/")


if __name__ == "__main__":
    print("=== 迁移调研报告 ===")
    mapping = migrate_reports() or {}

    print("\n=== 迁移外部资料 ===")
    migrate_financial_reports()

    print("\n=== 更新 wiki sources 路径 ===")
    update_wiki_sources(mapping)
    update_wiki_company_sources()

    print("\n=== 清理旧目录 ===")
    cleanup_old_dirs()

    print("\n=== 完成 ===")
    print(f"迁移了 {len(mapping)} 个报告文件")
