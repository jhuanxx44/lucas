import json
from typing import AsyncGenerator

from agents.config import load_config
from agents.manager import Manager

_manager = None


def get_manager() -> Manager:
    global _manager
    if _manager is None:
        config = load_config()
        _manager = Manager(config)
    return _manager


async def chat_event_stream(question: str) -> AsyncGenerator[str, None]:
    manager = get_manager()
    async for evt in manager.analyze_stream(question):
        event_type = evt["event"]
        data = json.dumps(evt["data"], ensure_ascii=False)
        yield f"event: {event_type}\ndata: {data}\n\n"
