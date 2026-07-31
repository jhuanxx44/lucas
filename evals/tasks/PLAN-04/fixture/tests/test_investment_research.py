from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPANIES = {
    "曜川电源": {
        "facts": ("42.0", "20.0%", "4.2", "30.0%", "2.1", "2.5", "55.0%", "68.0"),
        "report_facts": ("42.0", "20.0%", "4.2", "30.0%", "2.1"),
        "derived": (("10.0%",), ("50.0%", "0.50x", "0.5"), ("21.0",)),
        "risk": "海外收入占比较高，汇率与贸易政策变化可能影响盈利。",
        "catalyst": "海外大储订单进入集中交付期",
        "report_risk": ("汇率", "贸易政策"),
    },
    "澜岳储能": {
        "facts": ("36.0", "12.5%", "4.5", "34.0%", "5.4", "1.8", "30.0%", "52.0"),
        "report_facts": ("36.0", "12.5%", "4.5", "34.0%", "5.4"),
        "derived": (("12.5%",), ("120.0%", "1.20x", "1.2"), ("20.0",)),
        "risk": "前五大客户收入集中度较高，单一客户需求波动可能影响订单。",
        "catalyst": "工商业储能渠道扩张和新品认证",
        "report_risk": ("客户", "集中"),
    },
    "衡星电气": {
        "facts": ("30.0", "25.0%", "3.0", "28.0%", "-0.6", "2.2", "18.0%", "47.0"),
        "report_facts": ("30.0", "25.0%", "3.0", "28.0%", "-0.6"),
        "derived": (("10.0%",), ("-20.0%", "-0.20x", "-0.2"), ("20.0",)),
        "risk": "扩产期应收账款和资本开支上升，可能持续压制经营现金流。",
        "catalyst": "新建储能逆变器产线爬坡",
        "report_risk": ("应收账款", "资本开支", "经营现金流"),
    },
}


def test_company_pages_are_updated_from_their_own_reports_and_preserve_risks():
    for company, expected in COMPANIES.items():
        text = (ROOT / f"wiki/companies/电力设备/{company}.md").read_text()
        frontmatter = text.split("---", 2)[1]
        assert "summary:" in frontmatter
        assert "2026H1" in text
        assert all(value in text for value in expected["facts"])
        assert expected["risk"] in text
        assert f"sources/2026H1/{company}2026年半年度报告摘要.md" in text


def _report_path():
    reports = list((ROOT / "wiki/reports/电力设备").glob("*2026H1*.md"))
    assert len(reports) == 1
    return reports[0]


def test_report_compares_disclosed_and_derived_investment_dimensions():
    path = _report_path()
    text = path.read_text()
    assert text.startswith("---") and "summary:" in text.split("---", 2)[1]

    for company, expected in COMPANIES.items():
        assert company in text
        assert all(value in text for value in expected["report_facts"])
        assert all(any(option in text for option in alternatives) for alternatives in expected["derived"])
        assert all(value in text for value in expected["report_risk"])
        assert expected["catalyst"] in text
        assert f"sources/2026H1/{company}2026年半年度报告摘要.md" in text

    assert "sources/2026-07-30/估值快照.md" in text
    for label in ("来源", "计算", "净利率", "现金", "市盈率", "催化", "风险"):
        assert label in text


def test_report_contains_correct_growth_ranking_and_cash_quality_conclusion():
    text = _report_path().read_text()
    assert "增长最快" in text or "增速最快" in text
    assert all(company in text for company in ("衡星电气", "曜川电源", "澜岳储能"))

    assert "澜岳储能" in text and "现金质量" in text
    assert "衡星电气" in text and "经营现金流" in text and "为负" in text


def test_index_links_new_report_once_and_unrelated_files_remain_unchanged():
    index = (ROOT / "wiki/index.md").read_text()
    target = _report_path().relative_to(ROOT / "wiki").as_posix()
    assert index.count(target) == 1

    unrelated = (ROOT / "wiki/companies/电力设备/安沅设备.md").read_text()
    assert "本页不得因本次储能逆变器研究而修改。" in unrelated
    old_report = (ROOT / "wiki/reports/电力设备/2025储能逆变器回顾.md").read_text()
    assert "历史报告，不得覆盖。" in old_report
