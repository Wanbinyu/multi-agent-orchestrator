"""上下文自动压缩

当会话消息总 token 超过阈值时，把较旧的消息总结为一条摘要消息，
真正替换历史（而非仅写入记忆），从而释放上下文空间、避免撞模型窗口上限。
"""
from __future__ import annotations

from src.core.token_counter import count_messages_tokens, count_tokens
from src.gateway.client import GatewayClient
from src.models.schemas import ChatMessage, ToolResultContentBlock, ToolUseContentBlock


_COMPACTION_PROMPT = """请把以下对话历史压缩为一份简洁的摘要，保留对后续对话至关重要的信息：

- 用户的核心需求与已确定的决策
- 已完成的操作与工具调用结果的关键结论（不要保留冗长原始输出）
- 尚未完成的待办事项
- 关键的文件路径、配置、错误信息

要求：
- 用条目化的中文输出，控制在 600 字以内
- 不要编造未出现的信息
- 不要输出任何解释性前言，直接输出摘要内容

对话历史：
"""


class ContextCompactor:
    """上下文压缩器：超阈值时把旧消息替换为摘要"""

    def __init__(
        self,
        gateway: GatewayClient,
        max_context_tokens: int,
        threshold: float = 0.75,
        keep_recent: int = 6,
        min_messages_to_compact: int = 10,
    ):
        self.gateway = gateway
        self.max_context_tokens = max_context_tokens
        self.threshold = threshold
        self.keep_recent = keep_recent
        self.min_messages_to_compact = min_messages_to_compact

    @property
    def compact_limit(self) -> int:
        """触发压缩的 token 阈值"""
        return int(self.max_context_tokens * self.threshold)

    def needs_compaction(self, messages: list[ChatMessage]) -> bool:
        if self.max_context_tokens <= 0:
            return False
        if len(messages) < self.min_messages_to_compact:
            return False
        return count_messages_tokens(messages) > self.compact_limit

    def maybe_compact(self, messages: list[ChatMessage]) -> list[ChatMessage]:
        """若超阈值则压缩，返回（可能被替换的）新消息列表"""
        if not self.needs_compaction(messages):
            return messages

        # 拆分 system / 非系统消息
        system_msgs = [m for m in messages if m.role == "system"]
        non_system = [m for m in messages if m.role != "system"]

        # 不足保留量，无法压缩
        if len(non_system) <= self.keep_recent:
            return messages

        cut = len(non_system) - self.keep_recent
        while (
            cut > 0
            and self._has_tool_results(non_system[cut])
            and self._has_tool_uses(non_system[cut - 1])
        ):
            cut -= 1
        recent = non_system[cut:]
        old = non_system[:cut]
        if not old:
            return messages

        summary_text = self._summarize(old)
        if not summary_text.strip():
            return messages

        summary_msg = ChatMessage(
            role="user",
            content=(
                "[以下是之前对话的自动摘要，用于延续上下文]\n"
                f"{summary_text}\n"
                "[摘要结束]"
            ),
        )
        return system_msgs + [summary_msg] + recent

    @staticmethod
    def _has_tool_uses(message: ChatMessage) -> bool:
        return any(
            isinstance(block, ToolUseContentBlock)
            for block in message.content_blocks
        )

    @staticmethod
    def _has_tool_results(message: ChatMessage) -> bool:
        return any(
            isinstance(block, ToolResultContentBlock)
            for block in message.content_blocks
        )

    def _summarize(self, messages: list[ChatMessage]) -> str:
        """调用主模型把旧消息总结为文本"""
        transcript = self._build_transcript(messages)
        if not transcript.strip():
            return ""

        payload = [
            ChatMessage(role="system", content=_COMPACTION_PROMPT),
            ChatMessage(role="user", content=transcript),
        ]
        try:
            response = self.gateway.chat_with_main_model(
                messages=payload,
                task_id="compact",
                max_tokens=1024,
                temperature=0.2,
            )
            return response.content.strip()
        except Exception:
            # 压缩失败不应中断主流程，返回空串表示放弃本次压缩
            return ""

    @staticmethod
    def _build_transcript(messages: list[ChatMessage]) -> str:
        """把旧消息整理为纯文本，截断过长的工具结果"""
        lines: list[str] = []
        for msg in messages:
            content = msg.content
            # 工具结果块过长时截断
            if len(content) > 800:
                content = content[:800] + "…（已截断）"
            lines.append(f"{msg.role}: {content}")
        return "\n".join(lines)
