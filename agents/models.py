from dataclasses import dataclass, field
from typing import Optional
from utils.token_tracker import TokenUsage


@dataclass
class Task:
    question: str
    instruction: str = ""
    context: str = ""
    researcher_ids: list[str] = field(default_factory=list)
    mode: str = "parallel"


@dataclass
class ResearchResult:
    researcher_id: str
    researcher_name: str
    model: str
    content: str
    confidence: str = "medium"
    token_usage: Optional[TokenUsage] = None


@dataclass
class ManagerReport:
    question: str
    results: list[ResearchResult] = field(default_factory=list)
    synthesis: str = ""
    total_tokens: int = 0
