"""对话页面与 API 路由"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from src.core.agent import Agent, AgentTurnResult
from src.core.engineering import (
    DeliveryReportBuilder,
    RecoveryConfirmationRequired,
    RunJournalStore,
    SessionRecoveryManager,
    load_today_journals,
)
from src.core.session import Session, SessionStore
from src.gateway.client import GatewayClient
from src.gateway.errors import ProviderError
from src.models.schemas import (
    ApprovalMode,
    ChatStreamEvent,
    ExecutionDepthPreference,
    ModelRoutingMode,
)
from src.tools.paths import resolve_path
from src.tools.search_tools import PROJECT_TREE_IGNORED_DIRS

router = APIRouter()

_base_dir = Path(__file__).parent.parent
_templates = Jinja2Templates(directory=str(_base_dir / "templates"))

gateway: GatewayClient | None = None
store = SessionStore(base_dir="sessions")

# 当前正在流式响应的 Agent 实例，用于权限回调定位
active_agents: dict[str, Agent] = {}
_PROJECT_DIRECTORY_SCAN_LIMIT = 5000


def _get_gateway() -> GatewayClient:
    """Create the gateway only after first-run Provider configuration exists."""
    global gateway
    if gateway is not None:
        return gateway
    if not Path("config/providers.yaml").exists():
        raise HTTPException(
            status_code=409,
            detail="尚未配置 Provider，请先打开连接配置页面。",
        )
    try:
        gateway = GatewayClient()
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=409,
            detail="尚未配置 Provider，请先打开连接配置页面。",
        ) from exc
    return gateway


class CreateSessionForm(BaseModel):
    title: str = ""


class SendMessageForm(BaseModel):
    message: str = Field(..., min_length=1)


class UpdateModeForm(BaseModel):
    mode: ApprovalMode


class UpdateExecutionDepthForm(BaseModel):
    depth: ExecutionDepthPreference


class UpdateModelRoutingForm(BaseModel):
    mode: ModelRoutingMode


class UpdateAdversarialTestingForm(BaseModel):
    enabled: bool


class PermissionResponseForm(BaseModel):
    approved: bool


class UpdatePlanModeForm(BaseModel):
    action: Literal["enter", "revise", "approve", "cancel"]
    objective: str = ""
    feedback: str = ""


class UpdateRecoveryForm(BaseModel):
    action: Literal["continue", "abandon"]


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
    recovery = SessionRecoveryManager(session).inspect()
    return {
        "id": session.id,
        "title": session.title,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "approval_mode": session.approval_mode,
        "execution_depth": session.execution_depth,
        "model_routing_mode": session.model_routing_mode,
        "adversarial_testing": session.adversarial_testing,
        "plan_mode": session.plan_mode,
        "plan_artifact": session.plan_artifact.model_dump() if session.plan_artifact else None,
        "recovery": recovery.public_payload(),
        "messages": [m.model_dump() for m in session.messages],
    }


@router.post("/api/chat/sessions/{session_id}/recovery")
def update_session_recovery(
    session_id: str, form: UpdateRecoveryForm
) -> dict[str, Any]:
    try:
        session = store.load(session_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if session_id in active_agents:
        raise HTTPException(status_code=409, detail="会话仍有活跃请求，不能执行恢复决定")
    manager = SessionRecoveryManager(session)
    try:
        manager.decide(form.action)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    store.save(session)
    return {
        "success": True,
        "recovery": manager.inspect().public_payload(),
    }


@router.get("/api/chat/sessions/{session_id}/context")
def get_session_context(session_id: str) -> dict[str, Any]:
    """Return the deterministic local context budget without calling a model."""
    try:
        session = store.load(session_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Agent(_get_gateway(), session).get_context_status()


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


@router.get("/api/chat/sessions/{session_id}/report")
def get_session_delivery_report(
    session_id: str,
    scope: Literal["session", "today"] = "session",
) -> dict[str, Any]:
    """Return a local evidence report without invoking a Provider."""
    try:
        session = store.load(session_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if scope == "today":
        sessions_root = Path(session.output_dir).resolve().parent.parent
        journals = load_today_journals(sessions_root)
        report = DeliveryReportBuilder().build(journals, scope="today")
    else:
        journals = RunJournalStore.from_output_dir(session.output_dir).list()
        report = DeliveryReportBuilder().build(
            journals, scope="session", session_id=session.id
        )
    return report.model_dump()


@router.post("/api/chat/sessions/{session_id}/messages")
def send_message(session_id: str, form: SendMessageForm) -> dict[str, Any]:
    try:
        session = store.load(session_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if session_id in active_agents:
        raise HTTPException(status_code=409, detail="会话已有活跃请求，请等待其结束")

    try:
        SessionRecoveryManager(session).require_ready()
    except RecoveryConfirmationRequired as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    agent = Agent(_get_gateway(), session)
    active_agents[session_id] = agent
    try:
        result = agent.run_turn(form.message)
    finally:
        store.save(session)
        active_agents.pop(session_id, None)

    return result.model_dump()


@router.post("/api/chat/sessions/{session_id}/messages/stream")
async def send_message_stream(session_id: str, form: SendMessageForm):
    """流式发送消息，返回 Server-Sent Events"""
    try:
        session = store.load(session_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if session_id in active_agents:
        raise HTTPException(status_code=409, detail="会话已有活跃请求，请等待其结束")

    try:
        SessionRecoveryManager(session).require_ready()
    except RecoveryConfirmationRequired as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    agent = Agent(_get_gateway(), session)
    active_agents[session_id] = agent

    async def event_generator():
        try:
            async for event in agent.run_turn_stream(form.message):
                yield f"event: {event.type}\ndata: {event.model_dump_json()}\n\n"
        except Exception as e:
            if isinstance(e, ProviderError):
                ev = ChatStreamEvent(
                    type="error",
                    error=e.user_message,
                    error_code=e.code,
                    action=e.action,
                    retryable=e.retryable,
                )
            else:
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
        agent.session.approval_mode = form.mode

    return {"success": True, "mode": form.mode}


@router.post("/api/chat/sessions/{session_id}/depth")
def update_execution_depth(
    session_id: str, form: UpdateExecutionDepthForm
) -> dict[str, Any]:
    """Persist a user execution-depth preference for subsequent runs."""
    try:
        session = store.load(session_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    session.execution_depth = form.depth
    store.save(session)
    agent = active_agents.get(session_id)
    if agent is not None:
        agent.session.execution_depth = form.depth
    return {"success": True, "depth": form.depth}


@router.post("/api/chat/sessions/{session_id}/routing")
def update_model_routing(
    session_id: str, form: UpdateModelRoutingForm
) -> dict[str, Any]:
    """Persist automatic or fixed model routing for subsequent runs."""
    try:
        session = store.load(session_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    session.model_routing_mode = form.mode
    store.save(session)
    agent = active_agents.get(session_id)
    if agent is not None:
        agent.session.model_routing_mode = form.mode
    return {"success": True, "mode": form.mode}


@router.post("/api/chat/sessions/{session_id}/adversarial")
def update_adversarial_testing(
    session_id: str, form: UpdateAdversarialTestingForm
) -> dict[str, Any]:
    """Persist an explicit opt-in for the experimental read-only test role."""
    try:
        session = store.load(session_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if session_id in active_agents:
        raise HTTPException(
            status_code=409,
            detail="会话仍有活跃请求，对抗测试设置将在本轮结束后才能修改",
        )

    session.adversarial_testing = form.enabled
    store.save(session)
    return {"success": True, "enabled": form.enabled}


@router.get("/api/chat/sessions/{session_id}/plan")
def get_plan_mode(session_id: str) -> dict[str, Any]:
    try:
        session = store.load(session_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "state": session.plan_mode,
        "artifact": session.plan_artifact.model_dump() if session.plan_artifact else None,
    }


@router.post("/api/chat/sessions/{session_id}/plan")
def update_plan_mode(session_id: str, form: UpdatePlanModeForm) -> dict[str, Any]:
    implementation_request = ""
    try:
        session = store.load(session_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    try:
        if form.action == "enter":
            session.enter_plan_mode(form.objective)
        elif form.action == "revise":
            session.request_plan_revision(form.feedback)
        elif form.action == "approve":
            approved_plan = session.approve_plan()
            implementation_request = (
                "请严格按照下面已经批准的方案开始实施；遵守当前项目规则和权限规则，"
                "完成后运行与风险匹配的验证。\n\n" + approved_plan
            )
        else:
            session.cancel_plan_mode()
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    store.save(session)
    active = active_agents.get(session_id)
    if active is not None:
        active.session.plan_mode = session.plan_mode
        active.session.plan_artifact = session.plan_artifact
    return {
        "success": True,
        "state": session.plan_mode,
        "artifact": session.plan_artifact.model_dump() if session.plan_artifact else None,
        "implementation_request": implementation_request,
    }


@router.post("/api/chat/sessions/{session_id}/permission/{request_id}")
def respond_to_permission(
    session_id: str, request_id: str, form: PermissionResponseForm
) -> dict[str, Any]:
    """响应当前流式 Agent 的权限请求"""
    agent = active_agents.get(session_id)
    if agent is None:
        raise HTTPException(status_code=410, detail="会话当前没有活跃流式请求")

    if not agent.respond_to_permission(request_id, form.approved):
        raise HTTPException(status_code=404, detail="权限请求不存在或已经处理")
    return {"success": True, "approved": form.approved}


@router.delete("/api/chat/sessions/{session_id}")
def delete_session(session_id: str) -> dict[str, Any]:
    if not store.exists(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")
    if session_id in active_agents:
        raise HTTPException(status_code=409, detail="会话仍有活跃请求，不能删除")
    store.delete(session_id)
    return {"success": True}
