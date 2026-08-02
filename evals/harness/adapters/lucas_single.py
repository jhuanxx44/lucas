import os
from pathlib import Path

from evals.harness.models import AgentResult, RunLimits
from evals.harness.trace import TraceRecorder
from harness.config import build_single_system_prompt, load_agent_config
from harness.model_adapter import ResponsesModelAdapter
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
from utils.llm_client import create_client

PROMPT_PATH = Path(__file__).resolve().parents[3] / "prompts" / "harness" / "agent-loop.md"


class LucasSingleAgent:
    variant = "lucas-single"

    def __init__(self, model_adapter=None, wiki_recall_spec=None, variant=None,
                 context_window=None, keep_recent_steps=None, compression_level=None,
                 parallel_tool_calls=None):
        # client 延迟到 run() 建立；注入 model_adapter（测试）时不读取真实凭据。
        self.model_adapter = model_adapter
        self.wiki_recall_spec = wiki_recall_spec or WIKI_RECALL_SPEC
        # None = 走配置/环境；实验可用 LUCAS_CONTEXT_WINDOW=0 关闭压缩做 baseline
        self.context_window = context_window
        self.keep_recent_steps = keep_recent_steps
        self.compression_level = compression_level
        self.parallel_tool_calls = parallel_tool_calls
        if variant is not None:
            self.variant = variant

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
            self.wiki_recall_spec,
        ])
        model_adapter = self.model_adapter
        system_prompt = ""
        temperature = 0.0
        config = load_agent_config()
        context_window = self.context_window
        if context_window is None:
            env_window = os.environ.get("LUCAS_CONTEXT_WINDOW", "").strip()
            context_window = int(env_window) if env_window else config.model_context_window
        keep_recent_steps = self.keep_recent_steps
        if keep_recent_steps is None:
            env_keep = os.environ.get("LUCAS_KEEP_RECENT_STEPS", "").strip()
            keep_recent_steps = int(env_keep) if env_keep else config.context_keep_recent_steps
        compression_level = self.compression_level
        if compression_level is None:
            env_level = os.environ.get("LUCAS_COMPRESSION_LEVEL", "").strip()
            compression_level = int(env_level) if env_level else config.context_compression_level
        parallel_tool_calls = self.parallel_tool_calls
        if parallel_tool_calls is None:
            env_parallel = os.environ.get("LUCAS_PARALLEL_TOOL_CALLS", "").strip()
            parallel_tool_calls = env_parallel.lower() != "0" if env_parallel else True
        if model_adapter is None:
            system_prompt = build_single_system_prompt()
            temperature = config.temperature
            client = create_client(model=config.model, instructions=system_prompt)
            model_adapter = ResponsesModelAdapter(client)
        runner = AgentRunner(
            model_adapter,
            tools,
            load_prompt_template(PROMPT_PATH),
            instructions=system_prompt,
            temperature=temperature,
            context_window=context_window,
            keep_recent_steps=keep_recent_steps,
            compression_level=compression_level,
            parallel_tool_calls=parallel_tool_calls,
        )
        return await runner.run(instruction, allowed_tools, limits, trace)
