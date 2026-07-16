"""Provider 原生内容块与本地工具执行记录之间的转换。"""
from __future__ import annotations

from typing import Any

from src.models.schemas import (
    MessageContentBlock,
    TextContentBlock,
    ToolResultContentBlock,
    ToolUseContentBlock,
)


def native_tool_specs(blocks: list[MessageContentBlock]) -> list[dict[str, Any]]:
    return [
        {
            "tool": block.name,
            "params": dict(block.input),
            "tool_use_id": block.id,
        }
        for block in blocks
        if isinstance(block, ToolUseContentBlock)
    ]


def attach_tool_use_ids(
    calls: list[dict[str, Any]], specs: list[dict[str, Any]]
) -> None:
    """按本轮顺序把 Provider tool_use id 关联到本地执行结果。"""
    for call, spec in zip(calls, specs, strict=False):
        tool_use_id = spec.get("tool_use_id")
        if tool_use_id:
            call["tool_use_id"] = tool_use_id


def tool_result_blocks(
    calls: list[dict[str, Any]], follow_up: str = "请继续完成用户请求。"
) -> list[MessageContentBlock]:
    """生成 Anthropic 要求的结果优先内容数组。"""
    blocks: list[MessageContentBlock] = []
    for call in calls:
        tool_use_id = call.get("tool_use_id")
        if not tool_use_id:
            continue
        success = bool(call.get("success"))
        value = call.get("output") if success else call.get("error")
        blocks.append(
            ToolResultContentBlock(
                tool_use_id=str(tool_use_id),
                content=str(value or ("（无输出）" if success else "未知错误")),
                is_error=not success,
            )
        )
    if blocks and follow_up:
        blocks.append(TextContentBlock(text=follow_up))
    return blocks
