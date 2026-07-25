import logging

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from server.services.agent_stream import chat_event_stream

logger = logging.getLogger(__name__)
router = APIRouter()


class ChatRequest(BaseModel):
    question: str = Field(..., max_length=2000)
    history: list[dict] = []
    model: str = ""  # 空则用 lucas.yaml 默认；可选覆盖，如 "deepseek-v4-pro"


@router.post("/chat")
async def chat(req: ChatRequest, request: Request):
    user_id = request.state.user_id
    logger.info("chat request: %s (history=%d, user=%s, model=%s)",
                req.question[:80], len(req.history), user_id, req.model or "default")
    return StreamingResponse(
        chat_event_stream(req.question, req.history, user_id, model_override=req.model or None),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
