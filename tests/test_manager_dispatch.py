from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.manager import Manager
from agents.models import Task


@pytest.mark.asyncio
async def test_dispatch_falls_back_when_llm_returns_json_list(tmp_path):
    manager = object.__new__(Manager)
    manager.config = MagicMock()
    manager.config.researchers = [
        MagicMock(id="fundamental", name="基本面", expertise="财务分析"),
    ]
    manager.config.list_researcher_ids.return_value = ["fundamental"]
    manager._ws = MagicMock(wiki_root=str(tmp_path))
    manager.memory = MagicMock()
    manager.memory.get_memory_context.return_value = ""
    manager.client = MagicMock()
    manager.client.chat = AsyncMock(return_value=("[]", None))
    manager._load_prompt = MagicMock(
        return_value="{researchers_desc}\n{question}\n{wiki_context}\n{memory_context}"
    )

    action, task = await manager._dispatch("分析测试公司")

    assert action == "research"
    assert isinstance(task, Task)
    assert task.researcher_ids == ["fundamental"]


@pytest.mark.asyncio
async def test_tool_loop_accepts_single_object_wrapped_in_list(tmp_path):
    manager = object.__new__(Manager)
    manager._ws = MagicMock(wiki_root=str(tmp_path))
    manager.memory = MagicMock()
    manager.memory.get_memory_context.return_value = ""
    manager._toolkit = MagicMock()
    manager._toolkit.get_tools_description.return_value = ""
    manager._toolkit.execute.return_value = "未找到"
    manager.client = MagicMock()
    manager.client.chat = AsyncMock(
        return_value=('[{"action":"answer","reply":"可以正常回答"}]', None)
    )
    manager._load_prompt = MagicMock(
        return_value=(
            "{question}\n{memory_context}\n{wiki_context}\n"
            "{tools_desc}\n{tool_results}"
        )
    )

    reply = await manager._tool_use_loop("测试问题")

    assert reply == "可以正常回答"
