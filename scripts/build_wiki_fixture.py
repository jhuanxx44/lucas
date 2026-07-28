"""通过 Firecrawl 抓取中文维基百科，激进清洗后构建检索 eval fixture。

v3 — 使用 onlyMainContent + 多遍清洗。
"""
import json, os, re, time
from pathlib import Path
from urllib.request import Request, urlopen

FIXTURE = Path(__file__).resolve().parents[1] / "evals" / "components" / "RETRIEVAL-BM25" / "fixture" / "wiki"

with open(Path(__file__).resolve().parents[1] / ".env") as f:
    API_KEY = [l.strip().split("=", 1)[1].strip() for l in f if l.startswith("FIRECRAWL_API_KEY=")][0]

ARTICLES = [
    ("companies/半导体", "中芯国际", "https://zh.wikipedia.org/wiki/%E4%B8%AD%E8%8A%AF%E5%9B%BD%E9%99%85"),
    ("companies/半导体", "台积电", "https://zh.wikipedia.org/wiki/%E5%8F%B0%E7%A9%8D%E9%9B%BB"),
    ("companies/半导体", "三星电子", "https://zh.wikipedia.org/wiki/%E4%B8%89%E6%98%9F%E9%9B%BB%E5%AD%90"),
    ("companies/半导体", "英特尔", "https://zh.wikipedia.org/wiki/%E8%8B%B1%E7%89%B9%E5%B0%94"),
    ("companies/半导体", "英伟达", "https://zh.wikipedia.org/wiki/%E8%8B%B1%E4%BC%9F%E8%BE%BE"),
    ("companies/半导体", "AMD", "https://zh.wikipedia.org/wiki/%E8%B6%85%E5%A8%81%E5%8D%8A%E5%AF%BC%E4%BD%93"),
    ("companies/半导体", "高通", "https://zh.wikipedia.org/wiki/%E9%AB%98%E9%80%9A"),
    ("companies/半导体", "海思半导体", "https://zh.wikipedia.org/wiki/%E6%B5%B7%E6%80%9D%E5%8D%8A%E5%AF%BC%E4%BD%93"),
    ("companies/半导体", "联发科", "https://zh.wikipedia.org/wiki/%E8%81%94%E5%8F%91%E7%A7%91%E6%8A%80"),
    ("companies/半导体", "SK海力士", "https://zh.wikipedia.org/wiki/SK%E6%B5%B7%E5%8A%9B%E5%A3%AB"),
    ("concepts", "半导体", "https://zh.wikipedia.org/wiki/%E5%8D%8A%E5%AF%BC%E4%BD%93"),
    ("concepts", "集成电路", "https://zh.wikipedia.org/wiki/%E9%9B%86%E6%88%90%E7%94%B5%E8%B7%AF"),
    ("concepts", "芯片设计", "https://zh.wikipedia.org/wiki/%E9%9B%86%E6%88%90%E7%94%B5%E8%B7%AF%E8%AE%BE%E8%AE%A1"),
    ("concepts", "晶圆", "https://zh.wikipedia.org/wiki/%E6%99%B6%E5%9C%86"),
    ("concepts", "微处理器", "https://zh.wikipedia.org/wiki/%E5%BE%AE%E5%A4%84%E7%90%86%E5%99%A8"),
    ("concepts", "存储器", "https://zh.wikipedia.org/wiki/%E5%AD%98%E5%82%A8%E5%99%A8"),
    ("concepts", "晶体管", "https://zh.wikipedia.org/wiki/%E6%99%B6%E4%BD%93%E7%AE%A1"),
    ("concepts", "摩尔定律", "https://zh.wikipedia.org/wiki/%E6%91%A9%E5%B0%94%E5%AE%9A%E5%BE%8B"),
    ("companies/光通信", "华为技术", "https://zh.wikipedia.org/wiki/%E5%8D%8E%E4%B8%BA"),
    ("companies/光通信", "中兴通讯", "https://zh.wikipedia.org/wiki/%E4%B8%AD%E5%85%B4%E9%80%9A%E8%AE%AF"),
    ("companies/光通信", "烽火通信", "https://zh.wikipedia.org/wiki/%E7%83%BD%E7%81%AB%E9%80%9A%E4%BF%A1"),
    ("companies/光通信", "诺基亚", "https://zh.wikipedia.org/wiki/%E8%AF%BA%E5%9F%BA%E4%BA%9A"),
    ("companies/光通信", "爱立信", "https://zh.wikipedia.org/wiki/%E7%88%B1%E7%AB%8B%E4%BF%A1"),
    ("concepts", "光纤通信", "https://zh.wikipedia.org/wiki/%E5%85%89%E7%BA%96%E9%80%9A%E4%BF%A1"),
    ("concepts", "激光器", "https://zh.wikipedia.org/wiki/%E6%BF%80%E5%85%89%E5%99%A8"),
    ("concepts", "波分复用", "https://zh.wikipedia.org/wiki/%E6%B3%A2%E5%88%86%E5%A4%8D%E7%94%A8"),
    ("concepts", "光放大器", "https://zh.wikipedia.org/wiki/%E5%85%89%E6%94%BE%E5%A4%A7%E5%99%A8"),
    ("concepts", "5G", "https://zh.wikipedia.org/wiki/5G"),
    ("concepts", "互联网", "https://zh.wikipedia.org/wiki/%E4%BA%92%E8%81%94%E7%BD%91"),
    ("concepts", "数据中心", "https://zh.wikipedia.org/wiki/%E6%95%B0%E6%8D%AE%E4%B8%AD%E5%BF%83"),
    # === 其他行业公司（检索干扰项）===
    ("companies/汽车", "特斯拉", "https://zh.wikipedia.org/wiki/%E7%89%B9%E6%96%AF%E6%8B%89_(%E5%85%AC%E5%8F%B8)"),
    ("companies/汽车", "比亚迪", "https://zh.wikipedia.org/wiki/%E6%AF%94%E4%BA%9A%E8%BF%AA"),
    ("companies/新能源", "隆基绿能", "https://zh.wikipedia.org/wiki/%E9%9A%86%E5%9F%BA%E7%BB%BF%E8%83%BD"),
    ("companies/新能源", "宁德时代", "https://zh.wikipedia.org/wiki/%E5%AE%81%E5%BE%B7%E6%97%B6%E4%BB%A3"),
    ("companies/消费电子", "苹果公司", "https://zh.wikipedia.org/wiki/%E8%8B%B9%E6%9E%9C%E5%85%AC%E5%8F%B8"),
    ("companies/软件服务", "微软", "https://zh.wikipedia.org/wiki/%E5%BE%AE%E8%BD%AF"),
    ("companies/互联网", "腾讯", "https://zh.wikipedia.org/wiki/%E8%85%BE%E8%AE%AF"),
    ("companies/互联网", "阿里巴巴", "https://zh.wikipedia.org/wiki/%E9%98%BF%E9%87%8C%E5%B7%B4%E5%B7%B4"),
    ("companies/食品饮料", "可口可乐", "https://zh.wikipedia.org/wiki/%E5%8F%AF%E5%8F%A3%E5%8F%AF%E4%B9%90"),
    ("companies/餐饮", "麦当劳", "https://zh.wikipedia.org/wiki/%E9%BA%A6%E5%BD%93%E5%8A%B3"),
    ("companies/体育用品", "耐克", "https://zh.wikipedia.org/wiki/%E8%80%90%E5%85%8B"),
    ("companies/餐饮", "星巴克", "https://zh.wikipedia.org/wiki/%E6%98%9F%E5%B7%B4%E5%85%8B"),
    # === 纯概念条目（检索干扰项）===
    ("concepts", "故宫", "https://zh.wikipedia.org/wiki/%E6%95%85%E5%AE%AB"),
    ("concepts", "长城", "https://zh.wikipedia.org/wiki/%E9%95%BF%E5%9F%8E"),
    ("concepts", "熊猫", "https://zh.wikipedia.org/wiki/%E5%A4%A7%E7%86%8A%E7%8C%AB"),
    ("concepts", "足球", "https://zh.wikipedia.org/wiki/%E8%B6%B3%E7%90%83"),
]


def clean_markdown(raw_md: str) -> str:
    """多遍激进清洗，返回干净正文。"""
    text = raw_md

    # P1: 全局干掉 [text](url) → text
    for _ in range(10):
        new_text = re.sub(r'\[([^\]]*?)\]\([^\)]*\)', r'\1', text)
        if new_text == text:
            break
        text = new_text

    # P2: 干掉裸 URL (以 https?:// 开头的行内片段)
    text = re.sub(r'\(https?://[^\s\)]*\)', '', text)
    text = re.sub(r'https?://[^\s\)\[\]]+', '', text)

    # P3: 干掉图片残留 ![...] 等
    text = re.sub(r'!\[.*?\]', '', text)

    # P4: 干掉 wiki 模板 {{...}}
    text = re.sub(r'\{\{[^}]*\}\}', '', text)

    # 分行处理
    lines = text.split('\n')
    cleaned = []
    in_table = False

    for line in lines:
        s = line.strip()

        # 跳空行
        if not s:
            if cleaned and cleaned[-1] != '':
                cleaned.append('')
            continue

        # 跳过表格行（| 开头，非标题行）
        if s.startswith('|') or s.startswith('|-'):
            if not in_table:
                in_table = True
            continue
        else:
            in_table = False

        # 跳过纯标记行
        if s in ('[编辑]', '[編輯]', '编辑', '編輯', '[]'):
            continue

        # 跳过 wiki 噪音短行
        noise_words = {'维基百科，自由的百科全书', '提示', '此条目', '此條目',
                       '关于', '關於', '跳转到内容', '切换目录', '目录',
                       '参见', '參見', '参考文献', '參考文獻', '外部链接', '外部連結',
                       '相关条目', '相關條目', '注释', '註釋', '备注', '備註',
                       '来源', '來源'}
        if s in noise_words or any(s.startswith(w) for w in noise_words):
            continue

        # 跳过 <...> 标签行
        if s.startswith('<') and s.endswith('>'):
            continue

        # 行内清洗
        # 干掉残留的引用编号 [1] [1][2] 等
        s = re.sub(r'\[(\d+(?:[,-]\d+)*)\]', '', s)
        # 干掉残留裸 URL
        s = re.sub(r'https?://[^\s\)\[\]（）\u4e00-\u9fff]*', '', s)
        # 压缩空格
        s = re.sub(r' {2,}', ' ', s).strip()

        if s and len(s) > 1:
            cleaned.append(s)

    # 去连续空行
    result = []
    for i, l in enumerate(cleaned):
        if l == '' and result and result[-1] == '':
            continue
        result.append(l)
    while result and result[0] == '':
        result.pop(0)
    while result and result[-1] == '':
        result.pop(-1)

    # Post: remove [\N\] footnote refs
    text = '\n'.join(result)
    text = re.sub(r'\[\\?\[?\d+(?:[,\-]\d+)*\\?\]?(?:\[?\\d+\\?\]?)?\]', '', text)
    # Remove \[ 编辑\] / \[编辑\] patterns
    text = re.sub(r'\\?\s*\[\s*编[辑輯]\s*\]', '', text)
    # Remove Telegram / Discord / IRC promo lines
    text = re.sub(r'\*\*維基百科志工.*?\*\*\s*(\(.*?\))?\s*', '', text)
    text = re.sub(r'中文維基百科\s+Facebook粉絲專頁.*?。\s*', '', text)
    # Remove ! prefix from standalone lines
    text = re.sub(r'^!\s*本页使用了标题或全文手工转换\s*$', '', text, flags=re.MULTILINE)
    # Remove ! prefix from lines (image caption remnants)
    text = re.sub(r'^!\s+', '', text, flags=re.MULTILINE)
    # Remove wiki Telegram/Discord promo
    text = re.sub(r'\*\*維基百科志願者互聯交流群\*\*.*?歡迎大家加入。\s*', '', text)
    text = re.sub(r'中文維基百科\s+Facebook粉絲專頁.*?關注。\s*', '', text)
    # Remove bare \ [编辑\] and \n\ [编辑\] variants
    text = re.sub(r'\\?\s*\[\s*编[辑輯]\s*\\?\]\s*', '', text)
    # Trim from 参见/参考文献/外部链接 sections onwards
    for header in ['参见', '參見', '参考文献', '參考文獻', '外部链接', '外部連結',
                   '相关条目', '相關條目', '注释', '註釋', '备注', '備註', '检索自']:
        text = re.sub(rf'\n##\s*{header}\s*\n.*$', '', text, flags=re.DOTALL)
    # Collapse consecutive blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def build_page(name: str, md: str, subdir: str) -> str:
    industry = subdir.split("/")[-1] if "/" in subdir else ""
    if "concepts" in subdir:
        fm = f"---\ntitle: {name}\ntype: concept\n---\n\n"
    
    else:
        fm = f"---\ntitle: {name}\ntype: company\nindustry: {industry}\n---\n\n"
    return fm + f"# {name}\n\n" + clean_markdown(md)


def scrape(url: str) -> str:
    payload = json.dumps({
        "url": url,
        "formats": ["markdown"],
        "onlyMainContent": True,
    }).encode("utf-8")
    req = Request(
        "https://api.firecrawl.dev/v1/scrape",
        data=payload,
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
    )
    with urlopen(req, timeout=45) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if not data.get("success"):
        raise RuntimeError(data.get("error", "unknown"))
    return data["data"]["markdown"]


def main():
    total = len(ARTICLES)
    success = 0
    too_short = 0
    failed = 0

    print(f"开始抓取 {total} 篇文章 (onlyMainContent)...\n")

    for i, (subdir, name, url) in enumerate(ARTICLES):
        print(f"[{i+1:2d}/{total}] {name:　<8s}", end=" ", flush=True)
        try:
            raw_md = scrape(url)
            page = build_page(name, raw_md, subdir)
            char_count = len(page)

            if char_count < 500:
                too_short += 1
                print(f"TOO SHORT: {char_count} chars")
            else:
                success += 1
                print(f"OK {char_count:>6,} chars")

            out_dir = FIXTURE / subdir
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / f"{name}.md").write_text(page, encoding="utf-8")

        except Exception as e:
            print(f"FAIL: {e}")
            failed += 1

        time.sleep(1.5)

    # Index
    lines = ["# Wiki 索引\n"]
    for d in sorted([d for d in FIXTURE.iterdir() if d.is_dir()]):
        for sub in sorted(d.iterdir()):
            if not sub.is_dir():
                continue
            lines.append(f"## {d.name} · {sub.name}\n")
            for f in sorted(sub.glob("*.md")):
                lines.append(f"- [{f.stem}]({d.name}/{sub.name}/{f.name})")
            lines.append("")
    (FIXTURE / "index.md").write_text("\n".join(lines), encoding="utf-8")

    total_pages = len(list(FIXTURE.rglob("*.md"))) - 1
    total_chars = sum(len(f.read_text()) for f in FIXTURE.rglob("*.md") if f.name != "index.md")
    avg_chars = total_chars // max(total_pages, 1)

    print(f"\n{'='*50}")
    print(f"结果: {success} 成功, {too_short} 太短, {failed} 失败")
    print(f"总计: {total_pages} 页, {total_chars:,} 字符, 平均 {avg_chars:,} 字符/页")


if __name__ == "__main__":
    main()
