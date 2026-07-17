"""会话存储"""
from __future__ import annotations

import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from src.models.schemas import ApprovalMode, ChatMessage, MessageContentBlock


class Session(BaseModel):
    """一个多轮对话会话"""

    id: str
    title: str = ""
    created_at: str
    updated_at: str
    messages: list[ChatMessage] = Field(default_factory=list)
    output_dir: str
    config_dir: str = "config"
    approval_mode: ApprovalMode = "auto"
    compaction_events: list[dict[str, Any]] = Field(default_factory=list)
    usage_observations: list[dict[str, Any]] = Field(default_factory=list)

    def add_message(
        self,
        role: str,
        content: str,
        content_blocks: list[MessageContentBlock] | None = None,
        provider_payload: list[dict[str, Any]] | None = None,
    ) -> ChatMessage:
        """添加一条消息并更新时间戳"""
        msg = ChatMessage(
            role=role,
            content=content,
            content_blocks=content_blocks or [],
            provider_payload=provider_payload or [],
        )
        self.messages.append(msg)
        self.updated_at = datetime.now(timezone.utc).isoformat()
        return msg

    def record_compaction_event(self, event: dict[str, Any]) -> None:
        """记录一次上下文压缩事件，最多保留最近 20 条。"""
        self.compaction_events.append(event)
        del self.compaction_events[:-20]
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def record_usage_observation(self, observation: dict[str, Any]) -> None:
        """记录一次本地估算与 Provider 实际 usage 的对比，最多保留最近 20 条。"""
        self.usage_observations.append(observation)
        del self.usage_observations[:-20]
        self.updated_at = datetime.now(timezone.utc).isoformat()


class SessionStore:
    """基于 YAML 文件的会话持久化"""

    def __init__(self, base_dir: str = "sessions"):
        self.base_dir = Path(base_dir)

    def create(self, title: str = "") -> Session:
        """创建新会话并持久化"""
        session_id = (
            datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
            + "-"
            + uuid.uuid4().hex[:6]
        )
        output_dir = str(self.base_dir / session_id / "output")
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        now = datetime.now(timezone.utc).isoformat()
        session = Session(
            id=session_id,
            title=title or session_id,
            created_at=now,
            updated_at=now,
            output_dir=output_dir,
            approval_mode="approve",
        )
        self.save(session)
        return session

    def _path(self, session_id: str) -> Path:
        return self.base_dir / f"{session_id}.yaml"

    def save(self, session: Session) -> None:
        """保存会话到 YAML"""
        self.base_dir.mkdir(parents=True, exist_ok=True)
        with open(self._path(session.id), "w", encoding="utf-8") as f:
            yaml.dump(
                session.model_dump(),
                f,
                allow_unicode=True,
                sort_keys=False,
                default_flow_style=False,
            )

    def load(self, session_id: str) -> Session:
        """从 YAML 加载会话"""
        path = self._path(session_id)
        if not path.exists():
            raise FileNotFoundError(f"会话不存在: {session_id}")
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return Session(**data)

    def list(self) -> list[Session]:
        """列出所有会话，按更新时间倒序（同秒时用 id 保证稳定）"""
        if not self.base_dir.exists():
            return []
        sessions: list[Session] = []
        for path in self.base_dir.glob("*.yaml"):
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            sessions.append(Session(**data))
        sessions.sort(key=lambda s: (s.updated_at, s.id), reverse=True)
        return sessions

    def delete(self, session_id: str) -> None:
        """删除会话及其输出目录"""
        self._path(session_id).unlink(missing_ok=True)
        shutil.rmtree(self.base_dir / session_id, ignore_errors=True)

    def exists(self, session_id: str) -> bool:
        return self._path(session_id).exists()
