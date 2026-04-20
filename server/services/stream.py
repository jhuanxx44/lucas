import json
from typing import AsyncGenerator

from agents.config import load_config
from agents.manager import Manager


async def chat_event_stream(question: str, history: list[dict] | None = None) -> AsyncGenerator[str, None]:
    try:
        config = load_config()
        manager = Manager(config)
        if history:
            for turn in history[-10:]:
                if turn.get("role") == "user" and turn.get("content"):
                    manager.memory.add_turn(turn["content"], "user", "")
                elif turn.get("role") == "assistant" and turn.get("content"):
                    manager.memory.add_turn("", "assistant", turn["content"])
        async for evt in manager.analyze_stream(question):
            event_type = evt["event"]
            data = json.dumps(evt["data"], ensure_ascii=False)
            yield f"event: {event_type}\ndata: {data}\n\n"
    except Exception as e:
        err = json.dumps({"message": str(e)}, ensure_ascii=False)
        yield f"event: error\ndata: {err}\n\n"
