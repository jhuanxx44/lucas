import json
import os
import re
import uuid
from datetime import datetime, timezone


_SESSION_ID_RE = re.compile(r"^[0-9a-f]{32}$")


class SessionNotFound(Exception):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SessionStore:
    def __init__(self, memory_root: str):
        self.root = os.path.join(memory_root, "sessions")

    def _path(self, session_id: str) -> str:
        if not _SESSION_ID_RE.fullmatch(session_id):
            raise SessionNotFound(session_id)
        return os.path.join(self.root, f"{session_id}.json")

    def _read(self, session_id: str) -> dict:
        path = self._path(session_id)
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError as exc:
            raise SessionNotFound(session_id) from exc

    def _write(self, session: dict) -> None:
        os.makedirs(self.root, exist_ok=True)
        path = self._path(session["id"])
        tmp_path = f"{path}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(session, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)

    def list(self) -> list[dict]:
        if not os.path.isdir(self.root):
            return []
        sessions = []
        for name in os.listdir(self.root):
            if not name.endswith(".json"):
                continue
            try:
                session = self._read(name[:-5])
            except (SessionNotFound, json.JSONDecodeError):
                continue
            sessions.append({
                "id": session["id"],
                "title": session["title"],
                "created_at": session["created_at"],
                "updated_at": session["updated_at"],
                "message_count": len(session.get("messages", [])),
            })
        sessions.sort(key=lambda item: item["updated_at"], reverse=True)
        return sessions

    def create(self, title: str = "") -> dict:
        timestamp = _now()
        session = {
            "id": uuid.uuid4().hex,
            "title": title.strip() or "新对话",
            "created_at": timestamp,
            "updated_at": timestamp,
            "messages": [],
        }
        self._write(session)
        return session

    def get(self, session_id: str) -> dict:
        return self._read(session_id)

    def rename(self, session_id: str, title: str) -> dict:
        session = self._read(session_id)
        session["title"] = title.strip() or "新对话"
        session["updated_at"] = _now()
        self._write(session)
        return session

    def replace_messages(self, session_id: str, messages: list[dict]) -> dict:
        session = self._read(session_id)
        session["messages"] = messages
        if session["title"] == "新对话":
            first_user_message = next(
                (message.get("content", "") for message in messages if message.get("role") == "user"),
                "",
            )
            if first_user_message:
                session["title"] = first_user_message.strip()[:30]
        session["updated_at"] = _now()
        self._write(session)
        return session

    def delete(self, session_id: str) -> None:
        path = self._path(session_id)
        try:
            os.remove(path)
        except FileNotFoundError as exc:
            raise SessionNotFound(session_id) from exc
