"""Harness agent 配置：从仓库根 lucas.yaml 读取

lucas.yaml 承载 runtime + single_agent 段；
M5 起新增 wiki 段：wiki 知识模块的领域本体（行业列表、索引标题等）。
"""
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml

from utils.providers import get_provider_model

DEFAULT_ALLOWED_TOOLS = [
    "read_file", "apply_patch", "list_files", "search", "write_file",
    "web_search", "stock_quote", "stock_kline", "wiki_recall",
]

_DEFAULT_PATH = Path(__file__).resolve().parent.parent / "lucas.yaml"
_SYSTEM_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "harness" / "lucas-system-prompt.md"


def build_single_system_prompt(tools_desc: str, current_date: str = "") -> str:
    """组装 single 模式的 system prompt：身份/策略模板 + 渲染好的工具说明。

    工具说明属于稳定指令层，随 system 一起下发（而非混进每轮变化的 user prompt）。
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
    return text.format(tools_desc=tools_desc, current_date=current_date)


@dataclass
class AgentConfig:
    provider: str = "deepseek"
    model: str = ""  # 解析后的实际模型名（provider 默认或 lucas.yaml 覆盖）
    temperature: float = 0.0
    max_steps: int = 10
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
    provider = agent.get("provider", "deepseek")
    return AgentConfig(
        provider=provider,
        model=get_provider_model(provider, agent.get("model")),
        temperature=float(agent.get("temperature", 0.0)),
        max_steps=int(agent.get("max_steps", 10)),
        allowed_tools=list(agent.get("allowed_tools") or DEFAULT_ALLOWED_TOOLS),
        name=agent.get("name", "Lucas"),
        agent_mode=runtime.get("agent_mode", "single"),
    )


@dataclass
class WikiConfig:
    """wiki 知识模块（server/services/knowledge.py）的领域配置"""

    provider: str = "deepseek"
    model: str = ""  # 解析后的实际模型名（provider 默认或 lucas.yaml 覆盖）
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
    provider = wiki.get("provider", "deepseek")
    industries = wiki.get("industries") or []
    return WikiConfig(
        provider=provider,
        model=get_provider_model(provider, wiki.get("model")),
        industries=[str(i) for i in industries],
        index_title=str(wiki.get("index_title") or "Lucas 知识库索引"),
        source_max_chars=int(wiki.get("source_max_chars", 8000)),
    )
