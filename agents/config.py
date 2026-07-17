import os
import yaml
from dataclasses import dataclass, field
from typing import Optional

from utils.providers import get_provider_model, load_providers


@dataclass
class ResearcherConfig:
    id: str
    name: str
    model: str
    provider: str
    expertise: str
    system_prompt: str
    enable_search: bool = True
    data_types: list[str] = None

    def __post_init__(self):
        if self.data_types is None:
            self.data_types = []


@dataclass
class ManagerConfig:
    model: str
    provider: str
    system_prompt: str


@dataclass
class RuntimeConfig:
    agent_mode: str = "single"

    def __post_init__(self):
        if self.agent_mode not in {"single", "multi"}:
            raise ValueError(
                f"runtime.agent_mode must be 'single' or 'multi', got {self.agent_mode!r}"
            )


@dataclass
class SingleAgentConfig:
    name: str
    model: str
    provider: str
    expertise: str
    prompt: str
    enable_search: bool = True
    data_types: list[str] = None

    def __post_init__(self):
        if self.data_types is None:
            self.data_types = []


@dataclass
class AgentsConfig:
    manager: ManagerConfig
    researchers: list[ResearcherConfig]
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)
    single_agent: Optional[SingleAgentConfig] = None

    def get_researcher(self, researcher_id: str) -> Optional[ResearcherConfig]:
        for r in self.researchers:
            if r.id == researcher_id:
                return r
        return None

    def list_researcher_ids(self) -> list[str]:
        return [r.id for r in self.researchers]


def load_config(config_path: str = None) -> AgentsConfig:
    if config_path is None:
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "agents.yaml")

    # 加载 providers 配置
    providers_config = load_providers()

    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    runtime = RuntimeConfig(agent_mode=raw.get("runtime", {}).get("agent_mode", "single"))

    # 解析 manager
    manager_raw = raw["manager"]
    manager_provider = manager_raw.get("provider", "deepseek")
    manager_model_override = manager_raw.get("model")
    manager_model = get_provider_model(manager_provider, manager_model_override)

    manager = ManagerConfig(
        model=manager_model,
        provider=manager_provider,
        system_prompt=manager_raw["system_prompt"],
    )

    # 解析 single agent
    single_raw = raw.get("single_agent", {})
    single_provider = single_raw.get("provider", "deepseek")
    single_model = get_provider_model(single_provider, single_raw.get("model"))
    single_agent = SingleAgentConfig(
        name=single_raw.get("name", "Lucas"),
        model=single_model,
        provider=single_provider,
        expertise=single_raw.get("expertise", ""),
        prompt=single_raw.get("prompt", "single-agent"),
        enable_search=single_raw.get("enable_search", True),
        data_types=single_raw.get("data_types", []),
    )

    # 解析 researchers
    researchers = []
    for r in raw.get("researchers", []):
        researcher_provider = r.get("provider", "deepseek")
        researcher_model_override = r.get("model")
        researcher_model = get_provider_model(researcher_provider, researcher_model_override)

        researchers.append(ResearcherConfig(
            id=r["id"],
            name=r["name"],
            model=researcher_model,
            provider=researcher_provider,
            expertise=r.get("expertise", ""),
            system_prompt=r.get("system_prompt", ""),
            enable_search=r.get("enable_search", True),
            data_types=r.get("data_types", []),
        ))

    return AgentsConfig(
        manager=manager,
        researchers=researchers,
        runtime=runtime,
        single_agent=single_agent,
    )
