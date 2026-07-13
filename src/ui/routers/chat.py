"""对话页面与 API 路由"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from src.core.agent import Agent, AgentTurnResult
from src.core.session import Session, SessionStore
from src.gateway.client import GatewayClient
from src.models.schemas import ApprovalMode, ChatStreamEvent

router = APIRouter()

_base_dir = Path(__file__).parent.parent
_templates = Jinja2Templates(directory=str(_base_dir / "templates"))

gateway = GatewayClient()
store = SessionStore(base_dir="sessions")

# 当前正在流式响应的 Agent 实例，用于权限回调定位
active_agents: dict[str, Agent] = {}


class CreateSessionForm(BaseModel):
    title: str = ""


class SendMessageForm(BaseModel):
    message: str = Field(..., min_length=1)


class UpdateModeForm(BaseModel):
    mode: ApprovalMode


class PermissionResponseForm(BaseModel):
    approved: bool


class SessionSummary(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str


@router.get("/chat")
async def chat_page(request: Request):
    return _templates.TemplateResponse(request, "chat.html")


@router.get("/api/chat/sessions")
def list_sessions() -> dict[str, Any]:
    sessions = store.list()
    return {
        "sessions": [
            SessionSummary(
                id=s.id,
                title=s.title,
                created_at=s.created_at,
                updated_at=s.updated_at,
            )
            for s in sessions
        ]
    }


@router.post("/api/chat/sessions")
def create_session(form: CreateSessionForm) -> dict[str, Any]:
    session = store.create(title=form.title)
    return {
        "session_id": session.id,
        "title": session.title,
        "created_at": session.created_at,
    }


@router.get("/api/chat/sessions/{session_id}")
def get_session(session_id: str) -> dict[str, Any]:
    try:
        session = store.load(session_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {
        "id": session.id,
        "title": session.title,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "approval_mode": session.approval_mode,
        "messages": [m.model_dump() for m in session.messages],
    }


@router.post("/api/chat/sessions/{session_id}/messages")
def send_message(session_id: str, form: SendMessageForm) -> dict[str, Any]:
    try:
        session = store.load(session_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    agent = Agent(gateway, session)
    result = agent.run_turn(form.message)
    store.save(session)

    return result.model_dump()


@router.post("/api/chat/sessions/{session_id}/messages/stream")
async def send_message_stream(session_id: str, form: SendMessageForm):
    """流式发送消息，返回 Server-Sent Events"""
    try:
        session = store.load(session_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    agent = Agent(gateway, session)
    active_agents[session_id] = agent

    async def event_generator():
        try:
            async for event in agent.run_turn_stream(form.message):
                yield f"event: {event.type}\ndata: {event.model_dump_json()}\n\n"
            store.save(session)
        except Exception as e:
            ev = ChatStreamEvent(type="error", error=str(e))
            yield f"event: error\ndata: {ev.model_dump_json()}\n\n"
        finally:
            active_agents.pop(session_id, None)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
    )


@router.post("/api/chat/sessions/{session_id}/mode")
def update_mode(session_id: str, form: UpdateModeForm) -> dict[str, Any]:
    """更新会话权限模式"""
    try:
        session = store.load(session_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    session.approval_mode = form.mode
    store.save(session)

    # 如果当前有活跃 Agent，同步更新其模式
    agent = active_agents.get(session_id)
    if agent is not None:
        agent.approval_mode = form.mode

    return {"success": True, "mode": form.mode}


@router.post("/api/chat/sessions/{session_id}/permission/{request_id}")
def respond_to_permission(
    session_id: str, request_id: str, form: PermissionResponseForm
) -> dict[str, Any]:
    """响应当前流式 Agent 的权限请求"""
    agent = active_agents.get(session_id)
    if agent is None:
        raise HTTPException(status_code=410, detail="会话当前没有活跃流式请求")

    agent.respond_to_permission(request_id, form.approved)
    return {"success": True, "approved": form.approved}


@router.delete("/api/chat/sessions/{session_id}")
def delete_session(session_id: str) -> dict[str, Any]:
    if not store.exists(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")
    store.delete(session_id)
    active_agents.pop(session_id, None)
    return {"success": True}
