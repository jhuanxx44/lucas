import logging
from typing import AsyncGenerator

from agents.config import AgentsConfig, ResearcherConfig
from agents.models import ResearchResult, Task
from agents.researcher import run_researcher_stream
from utils.verify import verify_result

logger = logging.getLogger(__name__)


class SingleAgentService:

    def __init__(self, config: AgentsConfig, prompt_loader):
        single = config.single_agent
        if single is None:
            raise ValueError("single_agent config is required when agent_mode is 'single'")
        self.agent_config = ResearcherConfig(
            id="single",
            name=single.name,
            model=single.model,
            provider=single.provider,
            expertise=single.expertise,
            system_prompt=prompt_loader(single.prompt),
            enable_search=single.enable_search,
            data_types=single.data_types,
        )

    async def run(self, task: Task) -> AsyncGenerator[dict, None]:
        """运行一个通用 Agent，并保持现有 research SSE 事件兼容。"""
        rc = self.agent_config
        full_text = []
        meta = {}

        yield {"event": "researcher_start", "data": {"id": rc.id, "name": rc.name}}
        try:
            async for evt in run_researcher_stream(rc, task):
                if evt["event"] == "researcher_chunk":
                    full_text.append(evt["data"]["text"])
                    yield evt
                elif evt["event"] == "_meta":
                    meta = evt["data"]
        except Exception as e:
            logger.error("[%s] Agent 异常: %s", rc.name, e)
            yield {"event": "researcher_error", "data": {"id": rc.id, "message": str(e)}}

        result = ResearchResult(
            researcher_id=rc.id,
            researcher_name=rc.name,
            model=rc.model,
            content="".join(full_text) or "[分析失败]",
            token_usage=None,
            source_urls=meta.get("source_urls", []),
            market_data=meta.get("market_data", ""),
        )
        await verify_result(result)
        yield {"event": "researcher_done", "data": {"id": rc.id}}
        yield {"event": "_results", "data": {"results": [result]}}
