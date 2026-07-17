from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agents.knowledge_service import KnowledgeService
from agents.models import ManagerReport, ResearchResult


class FakeClient:
    async def chat(self, **kwargs):
        return "", None


def _workspace(tmp_path: Path):
    return SimpleNamespace(
        root=str(tmp_path),
        raw_root=str(tmp_path / "raw"),
        ingested_root=str(tmp_path / "ingested"),
        reports_root=str(tmp_path / "reports"),
        wiki_root=str(tmp_path / "wiki"),
        memory_root=str(tmp_path / "memory"),
    )


def _service(tmp_path: Path) -> KnowledgeService:
    ws = _workspace(tmp_path)
    Path(ws.raw_root).mkdir()
    Path(ws.wiki_root).mkdir()
    (Path(ws.wiki_root) / "index.md").write_text("# Test Wiki\n", encoding="utf-8")
    return KnowledgeService(FakeClient(), memory=None, prompt_loader=lambda _name: "", workspace=ws)


def _raw_snapshot(raw_root: str) -> list[tuple[str, bytes]]:
    root = Path(raw_root)
    return [
        (str(path.relative_to(root)), path.read_bytes())
        for path in sorted(root.rglob("*"))
        if path.is_file()
    ]


def test_archive_writes_reports_and_keeps_raw_immutable(tmp_path):
    service = _service(tmp_path)
    raw_marker = Path(service._raw_dir) / "user-input.md"
    raw_marker.write_text("immutable", encoding="utf-8")
    before = _raw_snapshot(service._raw_dir)
    report = ManagerReport(
        question="测试问题",
        title="测试报告",
        industry="测试行业",
        synthesis="综合结论",
        results=[
            ResearchResult(
                researcher_id="tester",
                researcher_name="测试员",
                model="test-model",
                content="研究内容",
            )
        ],
    )

    report_dir = Path(service.archive(report))

    assert report_dir.is_relative_to(Path(service._reports_dir))
    assert (report_dir / "tester.md").is_file()
    assert (report_dir / "meta.json").is_file()
    assert _raw_snapshot(service._raw_dir) == before
    wiki_report = next((Path(service._wiki_dir) / "reports").rglob("*.md"))
    assert "reports/测试行业/" in wiki_report.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_ingest_writes_ingested_and_keeps_raw_immutable(tmp_path):
    service = _service(tmp_path)
    raw_marker = Path(service._raw_dir) / "user-input.md"
    raw_marker.write_text("immutable", encoding="utf-8")
    before = _raw_snapshot(service._raw_dir)
    service.compile_from_raw = AsyncMock(return_value="编译完成")

    result = await service.ingest_source(
        content="收录内容",
        title="测试材料",
        industry="测试行业",
        company="测试公司",
    )

    saved_path = Path(service._ws.root) / result["path"]
    assert saved_path.is_relative_to(Path(service._ingested_dir))
    assert saved_path.is_file()
    assert _raw_snapshot(service._raw_dir) == before
    service.compile_from_raw.assert_awaited_once_with(
        {"scope": "specific", "sources": [result["path"]]},
        on_status=None,
    )
