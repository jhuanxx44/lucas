from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.config import RuntimeConfig, load_config
from agents.manager import Manager
from agents.models import ResearchResult, Task


def test_default_config_uses_single_agent_mode():
    config = load_config()

    assert config.runtime.agent_mode == "single"
    assert config.single_agent is not None
    assert config.single_agent.prompt == "single-agent"


def test_invalid_agent_mode_is_rejected():
    with pytest.raises(ValueError, match="runtime.agent_mode"):
        RuntimeConfig(agent_mode="hybrid")


class _FakeService:
    def __init__(self, results):
        self.results = results
        self.run_calls = 0
        self.synthesize = AsyncMock(return_value="综合结果")

    async def run(self, task):
        self.run_calls += 1
        yield {"event": "_results", "data": {"results": self.results}}


def _manager_for_research(mode: str, results):
    manager = object.__new__(Manager)
    manager.config = SimpleNamespace(runtime=RuntimeConfig(mode))
    manager._dispatch = AsyncMock(return_value=("research", Task(question="测试问题")))
    manager.single_agent_service = _FakeService(results[:1])
    manager.single_agent_service.agent_config = SimpleNamespace(id="single", name="Lucas")
    manager.research_service = _FakeService(results)
    manager.knowledge_service = SimpleNamespace(persist_report=AsyncMock())
    return manager


@pytest.mark.asyncio
async def test_single_mode_skips_multi_research_and_synthesis():
    result = ResearchResult("single", "Lucas", "test-model", "单 Agent 结果")
    manager = _manager_for_research("single", [result])

    events = [event async for event in manager.analyze("测试问题")]

    assert manager.single_agent_service.run_calls == 1
    assert manager.research_service.run_calls == 0
    manager.research_service.synthesize.assert_not_awaited()
    assert any(
        event == {"event": "synthesis_chunk", "data": {"text": "单 Agent 结果"}}
        for event in events
    )


@pytest.mark.asyncio
async def test_multi_mode_preserves_research_and_synthesis():
    results = [
        ResearchResult("fundamental", "基本面", "test-model", "结果一"),
        ResearchResult("technical", "技术面", "test-model", "结果二"),
    ]
    manager = _manager_for_research("multi", results)
    manager.config.get_researcher = MagicMock(
        side_effect=lambda rid: SimpleNamespace(id=rid, name=rid)
    )
    manager._dispatch = AsyncMock(return_value=(
        "research",
        Task(question="测试问题", researcher_ids=["fundamental", "technical"]),
    ))

    events = [event async for event in manager.analyze("测试问题")]

    assert manager.research_service.run_calls == 1
    assert manager.single_agent_service.run_calls == 0
    manager.research_service.synthesize.assert_awaited_once_with("测试问题", results)
    assert any(
        event == {"event": "synthesis_chunk", "data": {"text": "综合结果"}}
        for event in events
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["single", "multi"])
async def test_direct_action_is_unaffected_by_agent_mode(mode):
    manager = object.__new__(Manager)
    manager.config = SimpleNamespace(runtime=RuntimeConfig(mode))
    manager._dispatch = AsyncMock(return_value=("direct", "测试问题"))
    manager._tool_use_loop = AsyncMock(return_value="直接回答")
    manager.memory = MagicMock()

    events = [event async for event in manager.analyze("测试问题")]

    manager._tool_use_loop.assert_awaited_once_with("测试问题")
    assert {"event": "synthesis_chunk", "data": {"text": "直接回答"}} in events
