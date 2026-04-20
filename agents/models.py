from dataclasses import dataclass, field
from datetime import datetime
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
class VerificationIssue:
    dimension: str  # "url_provenance" | "url_liveness" | "data_crosscheck"
    severity: str   # "error" | "warning" | "info"
    message: str


@dataclass
class VerificationResult:
    issues: list[VerificationIssue] = field(default_factory=list)
    checked_at: str = ""

    @property
    def passed(self) -> bool:
        return not any(i.severity == "error" for i in self.issues)

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warning")

    def compute_confidence(self) -> str:
        if self.error_count > 0:
            return "low"
        if self.warning_count > 2:
            return "low"
        if self.warning_count > 0:
            return "medium"
        return "high"

    def to_markdown(self) -> str:
        if not self.issues:
            return "\n\n## 数据验证结果\n\n✓ 全部校验通过\n"
        lines = ["\n\n## 数据验证结果\n"]
        icons = {"error": "❌", "warning": "⚠️", "info": "ℹ️"}
        for issue in self.issues:
            icon = icons.get(issue.severity, "•")
            lines.append(f"- {icon} [{issue.dimension}] {issue.message}")
        lines.append(f"\n置信度: {self.compute_confidence()}")
        return "\n".join(lines) + "\n"


@dataclass
class ResearchResult:
    researcher_id: str
    researcher_name: str
    model: str
    content: str
    confidence: str = "medium"
    token_usage: Optional[TokenUsage] = None
    source_urls: list[dict] = field(default_factory=list)
    market_data: str = ""
    verification: Optional[VerificationResult] = None


@dataclass
class ManagerReport:
    question: str
    results: list[ResearchResult] = field(default_factory=list)
    synthesis: str = ""
    total_tokens: int = 0
