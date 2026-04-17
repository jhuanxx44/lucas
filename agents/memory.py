"""
Manager 记忆系统：三层记忆架构

1. conversation — 对话上下文（内存，会话级）
2. preferences  — 用户偏好（文件持久化）
3. conclusions  — 历史分析结论（文件持久化）
"""
import json
import logging
import os
from datetime import datetime
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

_MAX_CONCLUSIONS = 50


class ManagerMemory:
    def __init__(self, memory_dir: str):
        self.memory_dir = memory_dir
        os.makedirs(memory_dir, exist_ok=True)
        self._conversation: list[dict] = []
        self._prefs_path = os.path.join(memory_dir, "preferences.yaml")
        self._conclusions_path = os.path.join(memory_dir, "conclusions.jsonl")

    # ── 第 1 层：对话上下文（内存） ──────────────────────

    def add_turn(self, question: str, action: str, summary: str):
        self._conversation.append({
            "question": question,
            "action": action,
            "summary": summary[:200],
            "timestamp": datetime.now().strftime("%H:%M"),
        })

    def get_conversation_context(self, max_turns: int = 5) -> str:
        if not self._conversation:
            return ""
        recent = self._conversation[-max_turns:]
        lines = []
        for t in recent:
            lines.append(f"[{t['timestamp']}] 用户: {t['question']}")
            lines.append(f"  → ({t['action']}) {t['summary']}")
        return "\n".join(lines)

    # ── 第 2 层：用户偏好（文件） ──────────────────────

    def load_preferences(self) -> dict:
        try:
            with open(self._prefs_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except FileNotFoundError:
            return {}

    def save_preferences(self, prefs: dict):
        prefs["updated"] = datetime.now().strftime("%Y-%m-%d")
        with open(self._prefs_path, "w", encoding="utf-8") as f:
            yaml.dump(prefs, f, allow_unicode=True, default_flow_style=False)

    def get_preferences_context(self) -> str:
        prefs = self.load_preferences()
        if not prefs:
            return ""
        parts = []
        if prefs.get("watchlist"):
            parts.append(f"关注股票: {', '.join(prefs['watchlist'])}")
        if prefs.get("focus_industries"):
            parts.append(f"关注行业: {', '.join(prefs['focus_industries'])}")
        if prefs.get("risk_preference"):
            parts.append(f"风险偏好: {prefs['risk_preference']}")
        if prefs.get("analysis_style"):
            parts.append(f"分析风格: {prefs['analysis_style']}")
        if prefs.get("custom_notes"):
            for note in prefs["custom_notes"][-5:]:
                parts.append(f"备注: {note}")
        return "\n".join(parts)

    # ── 第 3 层：分析结论（文件） ──────────────────────

    def add_conclusion(
        self,
        question: str,
        topics: list[str],
        conclusion: str,
        sentiment: str = "neutral",
        researchers: list[str] = None,
    ):
        record = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "question": question,
            "topics": topics,
            "conclusion": conclusion,
            "sentiment": sentiment,
            "researchers": researchers or [],
        }
        lines = self._load_conclusion_lines()
        lines.append(json.dumps(record, ensure_ascii=False))
        if len(lines) > _MAX_CONCLUSIONS:
            lines = lines[-_MAX_CONCLUSIONS:]
        with open(self._conclusions_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    def find_related_conclusions(self, question: str, max_results: int = 3) -> str:
        lines = self._load_conclusion_lines()
        if not lines:
            return ""
        scored = []
        for line in lines:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            score = sum(1 for t in rec.get("topics", []) if t in question)
            if score > 0:
                scored.append((score, rec))
        scored.sort(key=lambda x: x[0], reverse=True)
        results = [r for _, r in scored[:max_results]]
        if not results:
            return ""
        parts = []
        for r in results:
            parts.append(
                f"[{r['date']}] {r['question']} → {r['conclusion']} ({r['sentiment']})"
            )
        return "\n".join(parts)

    def _load_conclusion_lines(self) -> list[str]:
        try:
            with open(self._conclusions_path, "r", encoding="utf-8") as f:
                return [l.strip() for l in f if l.strip()]
        except FileNotFoundError:
            return []

    # ── 统一输出 ──────────────────────────────────────

    def get_memory_context(self, question: str) -> str:
        sections = []

        conv = self.get_conversation_context()
        if conv:
            sections.append(f"### 对话历史\n{conv}")

        prefs = self.get_preferences_context()
        if prefs:
            sections.append(f"### 用户画像\n{prefs}")

        conclusions = self.find_related_conclusions(question)
        if conclusions:
            sections.append(f"### 历史分析\n{conclusions}")

        if not sections:
            return "（暂无记忆）"
        return "\n\n".join(sections)
