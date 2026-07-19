from pathlib import Path

from agents.config import load_config
from evals.harness.models import AgentResult, RunLimits
from evals.harness.trace import TraceRecorder
from harness.model_adapter import LLMClientAdapter
from harness.runner import AgentRunner, load_prompt_template
from harness.tools.filesystem import (
    APPLY_PATCH_SPEC,
    LIST_FILES_SPEC,
    READ_FILE_SPEC,
    WRITE_FILE_SPEC,
)
from harness.tools.process import make_run_tests_spec
from harness.tools.search import SEARCH_SPEC
from harness.tools.registry import ToolRuntime
from utils.json_extract import extract_json
from utils.llm_client import create_client

PROMPT_PATH = Path(__file__).resolve().parents[3] / "prompts" / "harness" / "tool-loop.md"


class LucasSingleAgent:
    variant = "lucas-single"

    def __init__(self, model_adapter=None):
        if model_adapter is None:
            single = load_config().single_agent
            client = create_client(provider=single.provider, model=single.model)
            model_adapter = LLMClientAdapter(client, temperature=0.0)
        self.model_adapter = model_adapter

    async def run(
        self,
        instruction: str,
        workspace: Path,
        allowed_tools: list[str],
        limits: RunLimits,
        trace: TraceRecorder,
    ) -> AgentResult:
        tools = ToolRuntime(workspace, [
            READ_FILE_SPEC,
            APPLY_PATCH_SPEC,
            LIST_FILES_SPEC,
            SEARCH_SPEC,
            WRITE_FILE_SPEC,
            make_run_tests_spec(),
        ])
        runner = AgentRunner(
            self.model_adapter, tools, load_prompt_template(PROMPT_PATH)
        )
        result = await runner.run(instruction, allowed_tools, limits, trace)
        if isinstance(result.answer, str):
            parsed = extract_json(result.answer)
            if isinstance(parsed, dict):
                result.answer = parsed
        return result
