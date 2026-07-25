from pathlib import Path

from evals.harness.models import AgentResult, RunLimits
from evals.harness.trace import TraceRecorder
from harness.config import build_single_system_prompt, load_agent_config
from harness.model_adapter import LLMClientAdapter
from harness.runner import AgentRunner, load_prompt_template
from harness.tools.business.stock import STOCK_KLINE_SPEC, STOCK_QUOTE_SPEC
from harness.tools.business.wiki import WIKI_RECALL_SPEC
from harness.tools.generic.filesystem import (
    APPLY_PATCH_SPEC,
    LIST_FILES_SPEC,
    READ_FILE_SPEC,
    SEARCH_SPEC,
    WRITE_FILE_SPEC,
)
from harness.tools.generic.web_search import WEB_SEARCH_SPEC
from harness.tools.generic.planning import UPDATE_PLAN_SPEC
from harness.tools.registry import ToolRuntime
from utils.json_extract import extract_json
from utils.llm_client import create_client

PROMPT_PATH = Path(__file__).resolve().parents[3] / "prompts" / "harness" / "agent-loop.md"


class LucasSingleAgent:
    variant = "lucas-single"

    def __init__(self, model_adapter=None):
        # client 延迟到 run() 建立：system prompt 需先渲染工具说明，而工具在 run() 才装配。
        # 注入 model_adapter（测试）时直接用，不建 client。
        self.model_adapter = model_adapter

    async def run(
        self,
        instruction: str,
        workspace: Path,
        allowed_tools: list[str],
        limits: RunLimits,
        trace: TraceRecorder,
    ) -> AgentResult:
        # 注册全部工具（超集）：评测含 READ/EDIT/WRITE 等框架级文件操作能力。
        # 线上聊天也开放这些工具，但写工具经 wiki/ 边界收窄（见 server/services/
        # agent_stream.py 的 _guard_wiki_write）。每题由 task.yaml 的 allowed_tools 逐题收窄。
        # 详见 evals/tasks/README.md「与线上聊天的关系」。
        tools = ToolRuntime(workspace, [
            READ_FILE_SPEC,
            APPLY_PATCH_SPEC,
            LIST_FILES_SPEC,
            SEARCH_SPEC,
            WRITE_FILE_SPEC,
            WEB_SEARCH_SPEC,
            UPDATE_PLAN_SPEC,
            STOCK_QUOTE_SPEC,
            STOCK_KLINE_SPEC,
            WIKI_RECALL_SPEC,
        ])
        model_adapter = self.model_adapter
        if model_adapter is None:
            # 工具说明渲染进 system prompt（稳定指令层），与产品聊天链路保持一致。
            config = load_agent_config()
            system_prompt = build_single_system_prompt(tools.describe(allowed_tools))
            client = create_client(provider=config.provider, model=config.model,
                                   system_prompt=system_prompt)
            model_adapter = LLMClientAdapter(client, temperature=config.temperature)
        runner = AgentRunner(
            model_adapter, tools, load_prompt_template(PROMPT_PATH)
        )
        result = await runner.run(instruction, allowed_tools, limits, trace)
        if isinstance(result.answer, str):
            parsed = extract_json(result.answer)
            if isinstance(parsed, dict):
                result.answer = parsed
        return result
