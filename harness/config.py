"""Harness agent 配置：从仓库根 lucas.yaml 读取

lucas.yaml 自 M2 起承载 agents.yaml 的 runtime + single_agent 段
（manager/researchers 段不迁移，agents/ 旧链路仍读 agents.yaml，M6 才删除）。
"""
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from utils.providers import get_provider_model

DEFAULT_ALLOWED_TOOLS = ["read_file", "apply_patch", "list_files", "search", "write_file"]

_DEFAULT_PATH = Path(__file__).resolve().parent.parent / "lucas.yaml"


@dataclass
class AgentConfig:
    provider: str = "deepseek"
    model: str = ""  # 解析后的实际模型名（provider 默认或 lucas.yaml 覆盖）
    temperature: float = 0.0
    max_steps: int = 10
    allowed_tools: list[str] = field(default_factory=lambda: list(DEFAULT_ALLOWED_TOOLS))
    name: str = "Lucas"
    prompt: str = "single-agent"
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
        prompt=agent.get("prompt", "single-agent"),
        agent_mode=runtime.get("agent_mode", "single"),
    )
