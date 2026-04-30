import logging

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from server.services.stream import chat_event_stream

logger = logging.getLogger(__name__)
router = APIRouter()


class ChatRequest(BaseModel):
    question: str = Field(..., max_length=2000)
    history: list[dict] = []


@router.post("/chat")
async def chat(req: ChatRequest, request: Request):
    user_id = request.state.user_id
    logger.info("chat request: %s (history=%d, user=%s)", req.question[:80], len(req.history), user_id)
    return StreamingResponse(
        chat_event_stream(req.question, req.history, user_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
