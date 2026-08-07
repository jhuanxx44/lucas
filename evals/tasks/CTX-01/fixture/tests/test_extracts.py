"""CTX-01 判卷：12 份抽取文件 + 汇总表必须与源备忘录一致。

本文件位于工作区内（pytest 必须在工作区里运行），Agent 有 read_file 权限就能读到它，
因此**不能内联期望值**——那等于把答案放进考场。期望值改为从 memos/ 现场解析并套用
规则.md 的评级规则得出：读到本文件只能看到规则（规则.md 本就公开），拿不到答案。

ground truth 的漂移保护放在工作区外的 tests/test_ctx_long_task_fixture.py，
那里钉住具体数值并校验本文件的推导与 generate_fixture.py 一致。
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ("code", "name", "revenue", "gross_margin", "risk", "rating")


def rating(gross_margin: float, risk: str) -> str:
    """规则.md 的评级规则；顺序判断，第一条命中即为结果。"""
    if gross_margin >= 40.0 and risk in ("低", "中"):
        return "A"
    if gross_margin >= 25.0:
        return "B"
    return "C"


def _truth_from_memo(path: Path) -> dict:
    """从备忘录原文解析出该公司的真值。"""
    text = path.read_text(encoding="utf-8")
    title = re.search(r"^#\s*(\S+)\s+(\S+)\s+尽职调查备忘录", text, flags=re.MULTILINE)
    revenue = re.search(r"\|\s*营业收入（万元）\s*\|\s*([\d.]+)\s*\|", text)
    margin = re.search(r"\|\s*综合毛利率（%）\s*\|\s*([\d.]+)\s*\|", text)
    risk = re.search(r"判定为：(\S)。", text)
    missing = [n for n, m in (("title", title), ("revenue", revenue),
                              ("margin", margin), ("risk", risk)) if m is None]
    assert not missing, f"{path.name} 无法解析字段 {missing}——fixture 结构已变"
    gross_margin = float(margin.group(1))
    return {
        "code": title.group(1),
        "name": title.group(2),
        "revenue": revenue.group(1),
        "gross_margin": f"{gross_margin:.1f}",
        "risk": risk.group(1),
        "rating": rating(gross_margin, risk.group(1)),
    }


def _expected() -> list[dict]:
    memos = sorted((ROOT / "memos").glob("*.md"))
    assert memos, "memos/ 为空——fixture 损坏"
    return [_truth_from_memo(memo) for memo in memos]


def _parse(text: str) -> dict:
    """解析 key: value 行；容忍空行、多余空格与全角冒号。"""
    parsed = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        match = re.match(r"^([A-Za-z_]+)\s*[:：]\s*(.+)$", line)
        if match:
            parsed[match.group(1).lower()] = match.group(2).strip()
    return parsed


def _numeric_equal(actual: str, expected: str) -> bool:
    """数值字段容忍 40 / 40.0 与千分位写法。"""
    try:
        return abs(float(actual.replace(",", "").rstrip("%").strip()) - float(expected)) < 0.05
    except ValueError:
        return False


def test_all_extract_files_exist_with_correct_values():
    missing, errors = [], []
    for want in _expected():
        code = want["code"]
        path = ROOT / "extracts" / f"{code}.txt"
        if not path.is_file():
            missing.append(f"extracts/{code}.txt")
            continue
        got = _parse(path.read_text(encoding="utf-8"))
        for field in FIELDS:
            expected, actual = want[field], got.get(field, "<缺失>")
            if field in ("revenue", "gross_margin"):
                if not _numeric_equal(actual, expected):
                    errors.append(f"{code}.{field}: got {actual!r}, want {expected!r}")
            elif actual != expected:
                errors.append(f"{code}.{field}: got {actual!r}, want {expected!r}")
    assert not missing, f"缺少抽取文件: {missing}"
    assert not errors, "抽取字段错误:\n" + "\n".join(errors)


def test_summary_table_covers_all_companies_with_correct_rating():
    path = ROOT / "汇总.md"
    assert path.is_file(), "缺少 汇总.md"
    text = path.read_text(encoding="utf-8")
    errors = []
    for want in _expected():
        code = want["code"]
        row = next((line for line in text.splitlines() if code in line), None)
        if row is None:
            errors.append(f"{code}: 汇总表缺少该行")
            continue
        cells = [cell.strip() for cell in row.strip().strip("|").split("|")]
        if want["name"] not in row:
            errors.append(f"{code}: 汇总行缺少名称 {want['name']}")
        if want["rating"] not in cells:
            errors.append(
                f"{code}: 汇总行评级应为 {want['rating']}，实际行为 {row.strip()!r}")
    assert not errors, "汇总表错误:\n" + "\n".join(errors)


def test_source_memos_are_present_and_unmodified_in_count():
    """源备忘录是只读输入；数量变化说明 fixture 被改动。"""
    memos = sorted((ROOT / "memos").glob("*.md"))
    assert len(memos) == 12, f"备忘录数量应为 12，实际 {len(memos)}"
