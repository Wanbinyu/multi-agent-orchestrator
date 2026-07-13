"""会话自动总结：将会话历史提取为长期记忆条目"""
from __future__ import annotations

from src.core.memory import MemoryCategory, MemoryStore
from src.core.session import Session
from src.gateway.client import GatewayClient
from src.models.schemas import ChatMessage, ChatResponse


_SUMMARIZE_PROMPT = """请阅读以下对话历史，从中提取对后续会话有用的关键信息。

只输出以下类别的条目，每行一条，格式严格为 `[类别] 内容`：
- [preference] 用户偏好、习惯、明确要求（如语言、风格、框架）
- [decision] 已做出的技术或产品决策
- [fact] 项目事实、关键概念、已确认的信息
- [project_structure] 项目结构、文件位置约定

如果某条目不明确，不要编造。如果没有可提取的内容，回复“无”。

对话历史：
"""


class SessionSummarizer:
    """基于主模型总结会话并写入记忆存储"""

    def __init__(
        self,
        gateway: GatewayClient,
        memory_store: MemoryStore | None = None,
        max_messages: int = 30,
    ):
        self.gateway = gateway
        self.memory_store = memory_store or MemoryStore()
        self.max_messages = max_messages

    def _build_transcript(self, session: Session) -> str:
        """把会话消息整理为纯文本，跳过 system 与工具结果"""
        lines: list[str] = []
        for msg in session.messages:
            if msg.role == "system":
                continue
            if msg.role == "user" and "[工具" in msg.content:
                # 工具结果过于冗长，跳过
                continue
            lines.append(f"{msg.role}: {msg.content[:500]}")
        return "\n".join(lines)

    def _parse_entries(self, text: str) -> list[tuple[MemoryCategory, str]]:
        """从模型输出中解析 `[category] content` 行"""
        entries: list[tuple[MemoryCategory, str]] = []
        allowed = {
            "preference",
            "decision",
            "fact",
            "project_structure",
            "session_summary",
            "code_symbol",
        }
        for line in text.strip().splitlines():
            line = line.strip()
            if not line.startswith("[") or "]" not in line:
                continue
            category, _, content = line[1:].partition("]")
            category = category.strip().lower()
            content = content.strip()
            if category in allowed and content:
                entries.append((category, content))  # type: ignore[arg-type]
        return entries

    def summarize(self, session: Session, source: str | None = None) -> list[str]:
        """总结会话并保存记忆条目，返回新增记忆 id 列表"""
        if not self.memory_store.config.enabled:
            return []

        transcript = self._build_transcript(session)
        if not transcript.strip():
            return []

        messages = [
            ChatMessage(role="system", content=_SUMMARIZE_PROMPT),
            ChatMessage(role="user", content=transcript),
        ]
        response: ChatResponse = self.gateway.chat_with_main_model(
            messages=messages,
            task_id=f"summarize-{session.id}",
            max_tokens=1024,
            temperature=0.2,
        )

        entries = self._parse_entries(response.content)
        if not entries:
            return []

        source = source or f"session:{session.id}"
        added_ids: list[str] = []
        for category, content in entries:
            entry = self.memory_store.add(
                category=category,
                content=content,
                source=source,
                tags=["auto_summary"],
            )
            added_ids.append(entry.id)
        return added_ids
