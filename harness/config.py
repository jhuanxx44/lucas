"""从仓库根 ``lucas.yaml`` 读取 Lucas 配置。"""
import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml

DEFAULT_ALLOWED_TOOLS = [
    "read_file", "apply_patch", "list_files", "search", "write_file",
    "web_search", "doubao_search", "stock_quote", "stock_kline", "wiki_recall",
    "update_plan",
]

_DEFAULT_PATH = Path(__file__).resolve().parent.parent / "lucas.yaml"
_SYSTEM_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "harness" / "lucas-system-prompt.md"
DEFAULT_MODEL = "deepseek-v4-flash"


def build_single_system_prompt(current_date: str = "") -> str:
    """组装 single 模式的 system prompt，只渲染当前日期。

    原生 Responses 工具通过 API schema 下发，不再拼进 prompt。
    current_date 为当前日期锚点（如 2026-07-21），只提供时间基准、不代表外部事实
    已更新至该日；留空时由调用方按 date.today() 填充。
    """
    if not current_date:
        current_date = date.today().isoformat()
    text = _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            text = text[end + 4:].lstrip("\n")
    return text.format(current_date=current_date)


def _resolve_model(configured_model: object) -> str:
    if configured_model is not None and str(configured_model).strip():
        return str(configured_model).strip()
    env_model = os.environ.get("DEEPSEEK_MODEL", "").strip()
    return env_model or DEFAULT_MODEL


@dataclass
class AgentConfig:
    model: str = DEFAULT_MODEL
    temperature: float = 0.0
    max_steps: int = 10
    # 阶段 1 Context 管理：模型上下文窗口（token），0 = 关闭压缩；压缩时保留最近 N 步
    model_context_window: int = 1_000_000
    context_keep_recent_steps: int = 1
    # 压缩等级：1 = 纯机械（实验 baseline），2 = 链式（低损丢弃→LLM 摘要→FIFO 兜底，默认最高）
    context_compression_level: int = 2
    allowed_tools: list[str] = field(default_factory=lambda: list(DEFAULT_ALLOWED_TOOLS))
    name: str = "Lucas"
    agent_mode: str = "single"


def load_agent_config(config_path: str | Path | None = None) -> AgentConfig:
    """读取 lucas.yaml 的 single_agent + runtime 段；缺文件或缺字段时用默认值"""
    path = Path(config_path) if config_path is not None else _DEFAULT_PATH
    raw = {}
    if path.is_file():
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    agent = raw.get("single_agent") or {}
    runtime = raw.get("runtime") or {}
    return AgentConfig(
        model=_resolve_model(agent.get("model")),
        temperature=float(agent.get("temperature", 0.0)),
        max_steps=int(agent.get("max_steps", 10)),
        model_context_window=int(agent.get("model_context_window", 1_000_000)),
        context_keep_recent_steps=int(agent.get("context_keep_recent_steps", 1)),
        context_compression_level=int(agent.get("context_compression_level", 2)),
        allowed_tools=list(agent.get("allowed_tools") or DEFAULT_ALLOWED_TOOLS),
        name=agent.get("name", "Lucas"),
        agent_mode=runtime.get("agent_mode", "single"),
    )


@dataclass
class WikiConfig:
    """wiki 知识模块（server/services/knowledge.py）的领域配置"""

    model: str = DEFAULT_MODEL
    industries: list[str] = field(default_factory=list)
    index_title: str = "Lucas 知识库索引"
    source_max_chars: int = 8000


def load_wiki_config(config_path: str | Path | None = None) -> WikiConfig:
    """读取 lucas.yaml 的 wiki 段（领域本体：行业列表、索引标题）；缺文件或缺字段时用默认值"""
    path = Path(config_path) if config_path is not None else _DEFAULT_PATH
    raw = {}
    if path.is_file():
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    wiki = raw.get("wiki") or {}
    industries = wiki.get("industries") or []
    return WikiConfig(
        model=_resolve_model(wiki.get("model")),
        industries=[str(i) for i in industries],
        index_title=str(wiki.get("index_title") or "Lucas 知识库索引"),
        source_max_chars=int(wiki.get("source_max_chars", 8000)),
    )
