from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from server.services.stream import chat_event_stream

router = APIRouter()


class ChatRequest(BaseModel):
    question: str = Field(..., max_length=2000)
    history: list[dict] = []


@router.post("/chat")
async def chat(req: ChatRequest):
    return StreamingResponse(
        chat_event_stream(req.question, req.history),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
