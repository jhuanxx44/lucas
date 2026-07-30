from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPANIES = {
    "星河芯片": ("28.4", "41.2%", "曜石云", "先进制程产能集中于单一代工厂。"),
    "云岚存储": ("19.7", "36.5%", "北辰终端", "存储价格周期可能造成库存减值。"),
    "远景封测": ("13.2", "24.8%", "星海汽车", "车规认证周期较长且客户导入存在不确定性。"),
}
OLD_FACTS = {
    "星河芯片": ("23.1", "38.6%", "晨曦数据"),
    "云岚存储": ("18.5", "35.2%", "启明电脑"),
    "远景封测": ("11.8", "26.1%", "远航电子"),
}


def test_all_company_pages_use_their_own_q3_facts_and_preserve_risks():
    for company, (revenue, margin, customer, risk) in COMPANIES.items():
        text = (ROOT / f"wiki/companies/电子/{company}.md").read_text()
        assert "2026Q3" in text
        assert revenue in text
        assert margin in text
        assert customer in text
        assert risk in text
        assert f"sources/2026Q3/{company}季度简报.md" in text
        assert all(old not in text for old in OLD_FACTS[company])


def test_comparison_is_created_after_consolidation_with_correct_ranking():
    path = ROOT / "wiki/reports/电子/2026Q3半导体公司对比.md"
    text = path.read_text()
    assert text.startswith("---") and "summary:" in text.split("---", 2)[1]
    for company, (revenue, margin, customer, _) in COMPANIES.items():
        assert all(value in text for value in (company, revenue, margin, customer))

    assert "营收排序" in text
    ranking = text[text.index("营收排序"):]
    positions = [ranking.index(name) for name in ("星河芯片", "云岚存储", "远景封测")]
    assert positions == sorted(positions)


def test_index_contains_exactly_one_link_to_new_report():
    index = (ROOT / "wiki/index.md").read_text()
    target = "reports/电子/2026Q3半导体公司对比.md"
    assert index.count(target) == 1
