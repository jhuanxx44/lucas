"""一次性修复：按 wiki/ 磁盘实际结构重建 index.md。

背景：早期 migrate_wiki_by_industry.py 把公司文件挪进行业子目录（如
companies/光通信/），但没同步 index.md，导致 index 里条目分类为"未分类"、
路径指向已不存在的 companies/未分类/...，与磁盘脱节，wiki_recall 按分类
字面匹配时召回不到这些页面。

parse_wiki_index 按磁盘目录扫描，结果是权威的。这里直接用它整体重写 index.md
（不走 rebuild_index 的"合并旧条目"逻辑，否则会留下旧的错误条目）。写前备份。
"""
import os
import shutil
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from utils.wiki_core import parse_wiki_index  # noqa: E402

WIKI_DIR = os.path.join(PROJECT_ROOT, "wiki")
INDEX_TITLE = "Lucas A股股市 Wiki 索引"


def render_index(wiki_dir: str, title: str) -> str:
    idx = parse_wiki_index(wiki_dir)
    lines = [f"# {title}", ""]
    for section in idx["sections"]:
        lines.append(f"## {section['title']}")
        for item in section["items"]:
            lines.append(f"- [{item['name']}]({item['path']})")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main():
    index_path = os.path.join(WIKI_DIR, "index.md")
    if os.path.isfile(index_path):
        backup = index_path + ".bak"
        shutil.copy2(index_path, backup)
        print(f"已备份现有 index.md -> {backup}")
    content = render_index(WIKI_DIR, INDEX_TITLE)
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(content)
    section_count = content.count("\n## ")
    entry_count = content.count("\n- [")
    print(f"已重建 {index_path}：{section_count} 个分节，{entry_count} 个条目")


if __name__ == "__main__":
    main()
