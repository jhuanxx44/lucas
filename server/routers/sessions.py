from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from server.services.session_store import SessionNotFound, SessionStore
from workspace import LocalWorkspace


router = APIRouter()


class CreateSessionRequest(BaseModel):
    title: str = Field(default="", max_length=80)


class RenameSessionRequest(BaseModel):
    title: str = Field(..., max_length=80)


class ReplaceMessagesRequest(BaseModel):
    messages: list[dict]


def get_session_store(request: Request) -> SessionStore:
    workspace = LocalWorkspace(request.state.user_id)
    return SessionStore(workspace.memory_root)


def _get_or_404(store: SessionStore, session_id: str) -> dict:
    try:
        return store.get(session_id)
    except SessionNotFound as exc:
        raise HTTPException(status_code=404, detail="Session not found") from exc


@router.get("")
def list_sessions(store: SessionStore = Depends(get_session_store)):
    return store.list()


@router.post("", status_code=201)
def create_session(req: CreateSessionRequest, store: SessionStore = Depends(get_session_store)):
    return store.create(req.title)


@router.get("/{session_id}")
def get_session(session_id: str, store: SessionStore = Depends(get_session_store)):
    return _get_or_404(store, session_id)


@router.patch("/{session_id}")
def rename_session(
    session_id: str,
    req: RenameSessionRequest,
    store: SessionStore = Depends(get_session_store),
):
    _get_or_404(store, session_id)
    return store.rename(session_id, req.title)


@router.put("/{session_id}/messages")
def replace_messages(
    session_id: str,
    req: ReplaceMessagesRequest,
    store: SessionStore = Depends(get_session_store),
):
    _get_or_404(store, session_id)
    return store.replace_messages(session_id, req.messages)


@router.delete("/{session_id}", status_code=204)
def delete_session(session_id: str, store: SessionStore = Depends(get_session_store)):
    _get_or_404(store, session_id)
    store.delete(session_id)
    return Response(status_code=204)
