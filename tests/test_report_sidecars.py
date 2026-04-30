import json
from unittest.mock import MagicMock

import pytest

from agents.knowledge_service import KnowledgeService
from agents.models import (
    ManagerReport,
    ResearchResult,
    VerificationIssue,
    VerificationResult,
)


class FakeClient:
    def __init__(self, response: str):
        self.response = response

    async def chat(self, **kwargs):
        return self.response, None


def _service(response: str) -> KnowledgeService:
    prompt = (
        "question={question}\n"
        "synthesis={synthesis}\n"
        "evidence={evidence_summary}\n"
    )
    ws = MagicMock()
    ws.wiki_root = "/tmp/test_wiki"
    ws.raw_root = "/tmp/test_raw"
    ws.root = "/tmp/test_workspace"
    return KnowledgeService(FakeClient(response), memory=None, prompt_loader=lambda _name: prompt, workspace=ws)


def test_build_evidence_from_sources_market_data_and_verification():
    report = ManagerReport(
        question="分析测试公司",
        results=[
            ResearchResult(
                researcher_id="fundamental",
                researcher_name="基本面分析师",
                model="test-model",
                content="测试内容",
                source_urls=[{"title": "测试来源", "url": "https://example.com/report"}],
                market_data="| 指标 | 数值 |\n| 最新价 | 10元 |",
                verification=VerificationResult(issues=[
                    VerificationIssue(
                        dimension="url_liveness",
                        severity="info",
                        message="链接不可达（超时或连接失败）: https://example.com/report",
                    ),
                    VerificationIssue(
                        dimension="data_crosscheck",
                        severity="warning",
                        message="股价偏差: 内容中为 12，数据源为 10，偏差 20%",
                    ),
                ]),
            )
        ],
    )

    evidence = _service('{"claims": []}').build_evidence(report)

    assert [e.id for e in evidence] == ["ev_001", "ev_002", "ev_003", "ev_004"]
    assert evidence[0].kind == "source"
    assert evidence[0].path_or_url == "https://example.com/report"
    assert evidence[0].verification_status == "warning"
    assert evidence[1].kind == "metric"
    assert evidence[1].verification_status == "warning"
    assert evidence[2].kind == "verification_issue"


@pytest.mark.asyncio
async def test_write_sidecars_with_claims(tmp_path):
    response = json.dumps({
        "claims": [
            {
                "type": "interpretation",
                "text": "测试公司的盈利质量改善。",
                "evidence_ids": ["ev_001"],
                "confidence": "medium",
                "assumptions": ["需求保持稳定"],
            }
        ]
    }, ensure_ascii=False)
    report = ManagerReport(
        question="分析测试公司",
        synthesis="测试公司的盈利质量改善。",
        results=[
            ResearchResult(
                researcher_id="fundamental",
                researcher_name="基本面分析师",
                model="test-model",
                content="测试内容",
                source_urls=[{"title": "测试来源", "url": "https://example.com/report"}],
                verification=VerificationResult(),
            )
        ],
    )

    await _service(response).write_sidecars(report, str(tmp_path))

    evidence_payload = json.loads((tmp_path / "evidence.json").read_text(encoding="utf-8"))
    claims_payload = json.loads((tmp_path / "claims.json").read_text(encoding="utf-8"))

    assert evidence_payload["status"] == "ok"
    assert evidence_payload["evidence"][0]["id"] == "ev_001"
    assert claims_payload["status"] == "ok"
    assert claims_payload["claims"][0]["id"] == "cl_001"
    assert claims_payload["claims"][0]["evidence_ids"] == ["ev_001"]


@pytest.mark.asyncio
async def test_write_sidecars_ignores_non_list_evidence_ids(tmp_path):
    response = json.dumps({
        "claims": [
            {
                "type": "interpretation",
                "text": "测试公司的盈利质量改善。",
                "evidence_ids": None,
                "confidence": "medium",
            },
            {
                "type": "risk",
                "text": "需求波动可能影响盈利。",
                "evidence_ids": ["ev_001"],
                "confidence": "medium",
            },
        ]
    }, ensure_ascii=False)
    report = ManagerReport(
        question="分析测试公司",
        synthesis="测试公司的盈利质量改善，但需求有波动风险。",
        results=[
            ResearchResult(
                researcher_id="fundamental",
                researcher_name="基本面分析师",
                model="test-model",
                content="测试内容",
                source_urls=[{"title": "测试来源", "url": "https://example.com/report"}],
                verification=VerificationResult(),
            )
        ],
    )

    await _service(response).write_sidecars(report, str(tmp_path))

    claims_payload = json.loads((tmp_path / "claims.json").read_text(encoding="utf-8"))

    assert claims_payload["status"] == "ok"
    assert len(claims_payload["claims"]) == 2
    assert claims_payload["claims"][0]["evidence_ids"] == []
    assert claims_payload["claims"][0]["confidence"] == "low"
    assert claims_payload["claims"][1]["evidence_ids"] == ["ev_001"]


@pytest.mark.asyncio
async def test_write_sidecars_keeps_report_flow_on_claim_extract_failure(tmp_path):
    report = ManagerReport(
        question="分析测试公司",
        synthesis="测试结论",
        results=[
            ResearchResult(
                researcher_id="fundamental",
                researcher_name="基本面分析师",
                model="test-model",
                content="测试内容",
            )
        ],
    )

    await _service("not json").write_sidecars(report, str(tmp_path))

    evidence_payload = json.loads((tmp_path / "evidence.json").read_text(encoding="utf-8"))
    claims_payload = json.loads((tmp_path / "claims.json").read_text(encoding="utf-8"))

    assert evidence_payload["status"] == "ok"
    assert claims_payload["status"] == "error"
    assert claims_payload["claims"] == []
    assert "error" in claims_payload
