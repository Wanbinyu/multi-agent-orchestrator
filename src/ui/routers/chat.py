"""对话页面与 API 路由"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from src.core.agent import Agent, AgentTurnResult
from src.core.engineering import RunJournalStore
from src.core.session import Session, SessionStore
from src.gateway.client import GatewayClient
from src.models.schemas import ApprovalMode, ChatStreamEvent
from src.tools.paths import resolve_path
from src.tools.search_tools import PROJECT_TREE_IGNORED_DIRS

router = APIRouter()

_base_dir = Path(__file__).parent.parent
_templates = Jinja2Templates(directory=str(_base_dir / "templates"))

gateway = GatewayClient()
store = SessionStore(base_dir="sessions")

# 当前正在流式响应的 Agent 实例，用于权限回调定位
active_agents: dict[str, Agent] = {}
_PROJECT_DIRECTORY_SCAN_LIMIT = 5000


class CreateSessionForm(BaseModel):
    title: str = ""


class SendMessageForm(BaseModel):
    message: str = Field(..., min_length=1)


class UpdateModeForm(BaseModel):
    mode: ApprovalMode


class PermissionResponseForm(BaseModel):
    approved: bool


class ProjectDirectoryForm(BaseModel):
    path: str = Field(default=".", min_length=1)
    include_hidden: bool = False
    max_entries: int = Field(default=500, ge=1, le=1000)


class ProjectFileForm(BaseModel):
    path: str = Field(..., min_length=1)
    max_chars: int = Field(default=20_000, ge=100, le=100_000)


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


@router.post("/api/chat/project/directory")
def list_project_directory(form: ProjectDirectoryForm) -> dict[str, Any]:
    """返回单层项目目录，供 WebUI 按需展开。"""
    try:
        directory = resolve_path(form.path, ".")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not directory.exists():
        raise HTTPException(status_code=404, detail=f"目录不存在：{form.path}")
    if not directory.is_dir():
        raise HTTPException(status_code=400, detail=f"不是目录：{form.path}")

    try:
        visible = []
        scan_truncated = False
        for scanned, entry in enumerate(directory.iterdir(), start=1):
            if scanned > _PROJECT_DIRECTORY_SCAN_LIMIT:
                scan_truncated = True
                break
            if entry.is_dir() and entry.name in PROJECT_TREE_IGNORED_DIRS:
                continue
            if not form.include_hidden and entry.name.startswith("."):
                continue
            visible.append(entry)
        visible.sort(key=lambda item: (not item.is_dir(), item.name.casefold(), item.name))
    except OSError as exc:
        raise HTTPException(status_code=403, detail=f"目录无法访问：{exc}") from exc

    truncated = scan_truncated or len(visible) > form.max_entries
    entries = []
    for entry in visible[: form.max_entries]:
        try:
            stat = entry.stat()
        except OSError:
            stat = None
        entries.append({
            "name": entry.name,
            "path": str(entry),
            "is_dir": entry.is_dir(),
            "is_symlink": entry.is_symlink(),
            "size": stat.st_size if stat and entry.is_file() else None,
            "modified_at": stat.st_mtime if stat else None,
        })
    return {
        "path": str(directory),
        "entries": entries,
        "truncated": truncated,
        "scan_limit": _PROJECT_DIRECTORY_SCAN_LIMIT,
        "ignored_directories": sorted(PROJECT_TREE_IGNORED_DIRS),
    }


@router.post("/api/chat/project/file")
def read_project_file(form: ProjectFileForm) -> dict[str, Any]:
    """读取受大小限制的文本文件预览，不提供任何写操作。"""
    try:
        file_path = resolve_path(form.path, ".")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"文件不存在：{form.path}")
    if not file_path.is_file():
        raise HTTPException(status_code=400, detail=f"不是文件：{form.path}")

    try:
        file_size = file_path.stat().st_size
        max_bytes = form.max_chars * 4 + 4
        with file_path.open("rb") as stream:
            raw = stream.read(max_bytes)
    except OSError as exc:
        raise HTTPException(status_code=403, detail=f"文件无法访问：{exc}") from exc
    if b"\x00" in raw[:8192]:
        raise HTTPException(status_code=415, detail="不支持预览二进制文件")

    try:
        content = raw.decode("utf-8-sig")
        encoding = "utf-8"
    except UnicodeDecodeError:
        content = raw.decode("utf-8", errors="replace")
        encoding = "utf-8-replace"
    truncated = file_size > len(raw) or len(content) > form.max_chars
    return {
        "path": str(file_path),
        "name": file_path.name,
        "content": content[: form.max_chars],
        "size": file_size,
        "encoding": encoding,
        "truncated": truncated,
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


@router.get("/api/chat/sessions/{session_id}/context")
def get_session_context(session_id: str) -> dict[str, Any]:
    """Return the deterministic local context budget without calling a model."""
    try:
        session = store.load(session_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Agent(gateway, session).get_context_status()


@router.get("/api/chat/sessions/{session_id}/runs")
def list_session_runs(session_id: str) -> dict[str, Any]:
    try:
        session = store.load(session_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    journals = RunJournalStore.from_output_dir(session.output_dir).list()
    return {
        "runs": [
            {
                **journal.event_payload(),
                "started_at": journal.started_at,
                "updated_at": journal.updated_at,
                "completed_at": journal.completed_at,
            }
            for journal in journals
        ]
    }


@router.get("/api/chat/sessions/{session_id}/runs/{run_id}")
def get_session_run(session_id: str, run_id: str) -> dict[str, Any]:
    try:
        session = store.load(session_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    run_store = RunJournalStore.from_output_dir(session.output_dir)
    try:
        return run_store.load(run_id).model_dump()
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/api/chat/sessions/{session_id}/messages")
def send_message(session_id: str, form: SendMessageForm) -> dict[str, Any]:
    try:
        session = store.load(session_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    agent = Agent(gateway, session)
    try:
        result = agent.run_turn(form.message)
    finally:
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
        except Exception as e:
            ev = ChatStreamEvent(type="error", error=str(e))
            yield f"event: error\ndata: {ev.model_dump_json()}\n\n"
        finally:
            store.save(session)
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
