from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from server.services.stream import chat_event_stream

router = APIRouter()


class ChatRequest(BaseModel):
    question: str
    history: list[dict] = []


@router.post("/chat")
async def chat(req: ChatRequest):
    return StreamingResponse(
        chat_event_stream(req.question),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
