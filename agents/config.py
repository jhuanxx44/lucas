import os
import yaml
from dataclasses import dataclass
from typing import Optional


@dataclass
class ResearcherConfig:
    id: str
    name: str
    model: str
    expertise: str
    system_prompt: str
    enable_search: bool = True


@dataclass
class ManagerConfig:
    model: str
    system_prompt: str


@dataclass
class AgentsConfig:
    manager: ManagerConfig
    researchers: list[ResearcherConfig]

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
    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    manager = ManagerConfig(
        model=raw["manager"]["model"],
        system_prompt=raw["manager"]["system_prompt"],
    )
    researchers = []
    for r in raw.get("researchers", []):
        researchers.append(ResearcherConfig(
            id=r["id"],
            name=r["name"],
            model=r["model"],
            expertise=r.get("expertise", ""),
            system_prompt=r.get("system_prompt", ""),
            enable_search=r.get("enable_search", True),
        ))
    return AgentsConfig(manager=manager, researchers=researchers)
