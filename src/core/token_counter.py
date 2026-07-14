"""Token 计数工具

优先使用 tiktoken（若安装），否则退化为基于 UTF-8 字节的粗略估算。
用于上下文窗口感知与自动压缩的触发判断。
"""
from __future__ import annotations

from typing import Iterable

from src.models.schemas import ChatMessage

try:
    import tiktoken  # type: ignore

    _ENCODER = None

    def _get_encoder():
        global _ENCODER
        if _ENCODER is None:
            try:
                _ENCODER = tiktoken.get_encoding("cl100k_base")
            except Exception:
                _ENCODER = False
        return _ENCODER
except Exception:  # pragma: no cover - tiktoken 未安装时
    def _get_encoder():
        return False


# 每条消息的固定开销（角色标记、分隔符等），近似值
_PER_MESSAGE_OVERHEAD = 4


def count_tokens(text: str) -> int:
    """估算一段文本的 token 数"""
    if not text:
        return 0
    encoder = _get_encoder()
    if encoder:
        try:
            return len(encoder.encode(text))
        except Exception:
            pass
    # 退化：UTF-8 字节数 / 3（中英文混合的经验值）
    return max(1, len(text.encode("utf-8")) // 3)


def count_message_tokens(message: ChatMessage) -> int:
    """估算单条消息的 token 数（含开销）"""
    return count_tokens(message.content) + _PER_MESSAGE_OVERHEAD


def count_messages_tokens(messages: Iterable[ChatMessage]) -> int:
    """估算消息列表的总 token 数"""
    return sum(count_message_tokens(m) for m in messages)
