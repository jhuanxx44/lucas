"""CTX-01 fixture 的自洽性：ground truth 三处一致，尺寸落在实验设计区间。

CTX-01 是长上下文压缩实验任务，ground truth 出现在三个地方：
generate_fixture.py 的 COMPANIES、fixture/tests/test_extracts.py 的 EXPECTED、
以及生成出的 reference。任一处漂移都会让实验结论失效，因此在此锁定。
"""
import importlib.util
import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TASK_DIR = PROJECT_ROOT / "evals" / "tasks" / "CTX-01"
FIXTURE = TASK_DIR / "fixture"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def generator():
    return _load("ctx01_generate", TASK_DIR / "generate_fixture.py")


@pytest.fixture(scope="module")
def grader():
    return _load("ctx01_grader", FIXTURE / "tests" / "test_extracts.py")


# ground truth 钉在工作区外：fixture/tests/test_extracts.py 位于工作区内、Agent 可读，
# 因此那里只放规则不放答案（否则等于把答案放进考场）。具体数值锁定在这里。
PINNED = [
    ("HX-001", "汇信精密", "128600", "42.3", "低", "A"),
    ("HX-002", "中远新材", "96400", "51.7", "中", "A"),
    ("HX-003", "泰和能源", "214800", "38.4", "低", "B"),
    ("HX-004", "昌盛电子", "73200", "44.1", "高", "B"),
    ("HX-005", "华通医药", "158900", "26.5", "中", "B"),
    ("HX-006", "明远化工", "187300", "18.2", "高", "C"),
    ("HX-007", "联创半导", "64500", "63.8", "低", "A"),
    ("HX-008", "恒益物流", "231700", "12.6", "中", "C"),
    ("HX-009", "瑞晶光电", "89100", "40.0", "中", "A"),
    ("HX-010", "安泰重工", "176200", "24.9", "低", "C"),
    ("HX-011", "立信软件", "51800", "55.2", "高", "B"),
    ("HX-012", "金鼎材料", "143500", "31.0", "低", "B"),
]


def test_generator_ground_truth_matches_pinned_values(generator):
    actual = [
        (code, name, str(revenue), f"{margin:.1f}", risk, generator.rating(margin, risk))
        for code, name, revenue, margin, risk in generator.COMPANIES
    ]
    assert actual == PINNED


def test_grader_derives_same_truth_from_memos_without_inlining_answers(grader):
    """工作区内的 grader 必须从 memos/ 现场解析出同一套真值，且自身不含答案。"""
    derived = [
        tuple(truth[field] for field in grader.FIELDS)
        for truth in grader._expected()
    ]
    assert derived == PINNED

    source = (FIXTURE / "tests" / "test_extracts.py").read_text(encoding="utf-8")
    for code, name, revenue, *_ in PINNED:
        assert name not in source, f"grader 内联了公司名 {name}——答案泄漏进考场"
        assert revenue not in source, f"grader 内联了营收 {revenue}——答案泄漏进考场"


def test_reference_files_match_generator(generator):
    reference = TASK_DIR / "reference" / "workspace"
    for code, name, revenue, margin, risk in generator.COMPANIES:
        content = (reference / "extracts" / f"{code}.txt").read_text(encoding="utf-8")
        assert f"code: {code}" in content
        assert f"revenue: {revenue}" in content
        assert f"rating: {generator.rating(margin, risk)}" in content
    summary = (reference / "汇总.md").read_text(encoding="utf-8")
    for code, name, *_ in generator.COMPANIES:
        assert code in summary and name in summary


def test_rating_rule_covers_all_three_grades_and_both_boundaries(generator):
    """规则的三档都要有样本，且两个边界值在场——否则 grader 判不出规则实现错误。"""
    ratings = {generator.rating(margin, risk)
               for _, _, _, margin, risk in generator.COMPANIES}
    assert ratings == {"A", "B", "C"}

    margins = {margin for _, _, _, margin, _ in generator.COMPANIES}
    assert 40.0 in margins, "缺少毛利率恰为 40.0 的边界样本"
    assert any(24.0 <= m < 25.0 for m in margins), "缺少毛利率略低于 25.0 的边界样本"

    # 高风险 + 高毛利必须落到 B，证明风险等级真的参与判定
    assert generator.rating(44.1, "高") == "B"


def test_memo_sizes_stay_in_experiment_design_range():
    """单篇 < read_file 默认 16000（一次可读全）；合计约为 12K 窗口触发线的 3-4 倍。

    触发线 = 12000*0.9 - min(16384, 12000*0.1) = 9600 token。
    区间失守则实验前提不成立，需重新调整篇幅并复算。
    """
    memos = sorted((FIXTURE / "memos").glob("*.md"))
    assert len(memos) == 12
    sizes = [len(memo.read_text(encoding="utf-8")) for memo in memos]
    assert max(sizes) < 16000, f"单篇超过 read_file 默认上限：{max(sizes)}"
    assert min(sizes) > 4000, f"单篇过短，压缩不易触发：{min(sizes)}"

    total_chars = sum(sizes)
    trigger_tokens = 12000 * 0.9 - min(16384, int(12000 * 0.1))
    # 0.35 是 runner 的 DEFAULT_TOKENS_PER_CHAR（保守偏低估中文）
    multiple = total_chars * 0.35 / trigger_tokens
    assert 2.0 <= multiple <= 5.0, (
        f"累计需求为触发线的 {multiple:.1f} 倍，超出设计区间 2-5 倍"
    )


def test_memos_are_distinct_so_model_cannot_skip_reading():
    """各篇正文必须不同，否则模型可能凭一篇推断其余，实验测不到真实读取成本。"""
    bodies = []
    for memo in sorted((FIXTURE / "memos").glob("*.md")):
        text = memo.read_text(encoding="utf-8")
        # 去掉标题与财务表（含公司特有数值），只比正文散文部分
        body = re.sub(r"\|.*?\|", "", text)
        body = re.sub(r"^#.*$", "", body, flags=re.MULTILINE)
        bodies.append(body)
    assert len(set(bodies)) == len(bodies), "存在正文完全相同的备忘录"


def test_extracts_dir_starts_empty():
    """extracts/ 必须是空目录（只含 .gitkeep）——否则 Agent 无需真的抽取。"""
    entries = [p.name for p in (FIXTURE / "extracts").iterdir()]
    assert entries == [".gitkeep"], f"extracts/ 应为空，实际含 {entries}"


def test_risk_level_is_only_stated_in_risk_section(generator):
    """风险等级只出现在「风险评估」一节，避免正文其他地方泄漏答案。"""
    for code, _, _, _, risk in generator.COMPANIES:
        text = (FIXTURE / "memos" / f"{code}.md").read_text(encoding="utf-8")
        assert f"判定为：{risk}" in text
        head = text.split("## 四、风险评估")[0]
        assert "判定为" not in head
