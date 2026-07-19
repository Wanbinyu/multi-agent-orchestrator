"""Layered context compaction with deterministic quality gates."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from src.core.token_counter import count_messages_tokens, count_tokens
from src.gateway.client import GatewayClient
from src.models.schemas import ChatMessage, ToolResultContentBlock, ToolUseContentBlock


_L0_MARKER = "[MAO_CONTEXT_LAYER:L0]"
_L1_MARKER = "[MAO_CONTEXT_LAYER:L1]"
_CHECKPOINT_MARKER = "[MAO_TASK_CHECKPOINT]"
_RUN_ID_RE = re.compile(r"\b\d{8}-\d{6}-\d{6}-[A-Za-z0-9_-]{6,}\b")
_FILE_RE = re.compile(
    r"(?<![\w.-])(?:[A-Za-z]:[\\/])?(?:[\w.@-]+[\\/])+[\w.@-]+\.[A-Za-z0-9]{1,12}"
)
_KEEP_RE = re.compile(r"\bKEEP:[^\s,;，；]+")

_COMPACTION_PROMPT = """请把以下对话历史压缩为严格 JSON，不要输出 Markdown 围栏或解释。

Schema：
{
  "schema_version": 1,
  "requirements": ["用户核心需求"],
  "decisions": ["已确认决策"],
  "evidence": ["工具或验证关键结论"],
  "files_changed": ["已修改文件路径"],
  "todos": ["未完成事项"],
  "risks": ["剩余风险"],
  "run_refs": ["run_id"],
  "output_files": ["会话输出或交付文件"]
}

规则：只保留历史中明确出现的事实；路径和 run_id 原样保留；各数组去重；没有内容时使用空数组。

对话历史：
"""


class StructuredCompactionSummary(BaseModel):
    schema_version: int = 1
    requirements: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    files_changed: list[str] = Field(default_factory=list)
    todos: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    run_refs: list[str] = Field(default_factory=list)
    output_files: list[str] = Field(default_factory=list)


class CompactionMetadata(BaseModel):
    applied: bool = False
    layers: list[str] = Field(default_factory=list)
    before_messages: int = 0
    after_messages: int = 0
    deduplicated_messages: int = 0
    schema_valid: bool = False
    fallback_used: bool = False
    fallback_reason: str = ""
    required_entities: list[str] = Field(default_factory=list)
    retained_entities: list[str] = Field(default_factory=list)
    entity_retention: float = 1.0
    task_relevance_ratio: float = 0.0
    quality_passed: bool = False
    checkpoint_count: int = 0
    artifact_path: str = ""


class ContextCompactor:
    """Compact old history into L0 references, L1 summary and L2 recent text."""

    def __init__(
        self,
        gateway: GatewayClient,
        max_context_tokens: int,
        threshold: float = 0.75,
        keep_recent: int = 6,
        min_messages_to_compact: int = 10,
        artifact_dir: str | Path | None = None,
        task_checkpoint: str = "",
    ):
        self.gateway = gateway
        self.max_context_tokens = max_context_tokens
        self.threshold = threshold
        self.keep_recent = keep_recent
        self.min_messages_to_compact = min_messages_to_compact
        self.artifact_dir = Path(artifact_dir) if artifact_dir else None
        self.task_checkpoint = task_checkpoint.strip()
        self.last_metadata = CompactionMetadata()

    @property
    def compact_limit(self) -> int:
        return int(self.max_context_tokens * self.threshold)

    def needs_compaction(self, messages: list[ChatMessage]) -> bool:
        if self.max_context_tokens <= 0:
            return False
        if len(messages) < self.min_messages_to_compact:
            return False
        return count_messages_tokens(messages) > self.compact_limit

    def maybe_compact(self, messages: list[ChatMessage]) -> list[ChatMessage]:
        self.last_metadata = CompactionMetadata(before_messages=len(messages))
        if not self.needs_compaction(messages):
            return messages

        system_msgs = [message for message in messages if message.role == "system"]
        non_system = [message for message in messages if message.role != "system"]
        checkpoints = [
            message for message in non_system if _CHECKPOINT_MARKER in message.content
        ]
        if self.task_checkpoint:
            checkpoints = [ChatMessage(
                role="user",
                content=f"{_CHECKPOINT_MARKER}\n{self.task_checkpoint}",
            )]
        compactable = [
            message for message in non_system if _CHECKPOINT_MARKER not in message.content
        ]
        if len(compactable) <= self.keep_recent:
            return messages

        cut = len(compactable) - self.keep_recent
        while (
            cut > 0
            and self._has_tool_results(compactable[cut])
            and self._has_tool_uses(compactable[cut - 1])
        ):
            cut -= 1
        recent = compactable[cut:]
        old = compactable[:cut]
        if not old:
            return messages

        previous_layers = [message for message in old if self._is_layer_message(message)]
        raw_old = [message for message in old if not self._is_layer_message(message)]
        deduplicated = self._deduplicate_plain_messages(raw_old)
        removed_duplicates = len(raw_old) - len(deduplicated)
        if not deduplicated:
            return messages

        summary_text = self._summarize(deduplicated)
        if not summary_text.strip():
            self.last_metadata.fallback_used = True
            self.last_metadata.fallback_reason = "summary_call_failed_or_empty"
            return messages

        required_entities = self._extract_entities(deduplicated)
        parsed, fallback_reason = self._parse_structured_summary(summary_text)
        schema_valid = parsed is not None
        if parsed is not None:
            rendered_summary = self._repair_structured_entities(parsed, required_entities)
        else:
            rendered_summary = self._repair_plain_entities(summary_text, required_entities)
        retained = [item for item in required_entities if item in rendered_summary]
        retention = len(retained) / len(required_entities) if required_entities else 1.0
        entity_tokens = sum(count_tokens(item) for item in retained)
        relevance = min(1.0, entity_tokens / max(1, count_tokens(rendered_summary)))

        layered_messages: list[ChatMessage] = []
        if previous_layers:
            layered_messages.append(
                ChatMessage(role="user", content=self._build_l0_index(previous_layers))
            )
        artifact_path = self._persist_l1_artifact(
            rendered_summary, structured=schema_valid
        )
        artifact_ref = f"\n[artifact:{artifact_path}]" if artifact_path else ""
        layered_messages.append(ChatMessage(
            role="user",
            content=(
                f"{_L1_MARKER}{artifact_ref}\n{rendered_summary}\n"
                "[/MAO_CONTEXT_LAYER:L1]"
            ),
        ))
        result = system_msgs + layered_messages + checkpoints + recent
        layers = (["L0"] if previous_layers else []) + ["L1", "L2"]
        self.last_metadata = CompactionMetadata(
            applied=len(result) < len(messages),
            layers=layers,
            before_messages=len(messages),
            after_messages=len(result),
            deduplicated_messages=removed_duplicates,
            schema_valid=schema_valid,
            fallback_used=not schema_valid,
            fallback_reason=fallback_reason,
            required_entities=required_entities,
            retained_entities=retained,
            entity_retention=round(retention, 4),
            task_relevance_ratio=round(relevance, 4),
            quality_passed=retention >= 0.9,
            checkpoint_count=len(checkpoints),
            artifact_path=artifact_path,
        )
        return result if self.last_metadata.applied else messages

    @staticmethod
    def _is_layer_message(message: ChatMessage) -> bool:
        return _L0_MARKER in message.content or _L1_MARKER in message.content

    @staticmethod
    def _deduplicate_plain_messages(messages: list[ChatMessage]) -> list[ChatMessage]:
        result: list[ChatMessage] = []
        seen: set[tuple[str, str]] = set()
        for message in messages:
            if message.content_blocks or message.provider_payload:
                result.append(message)
                continue
            fingerprint = (message.role, message.content.strip())
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            result.append(message)
        return result

    @staticmethod
    def _has_tool_uses(message: ChatMessage) -> bool:
        return any(
            isinstance(block, ToolUseContentBlock) for block in message.content_blocks
        )

    @staticmethod
    def _has_tool_results(message: ChatMessage) -> bool:
        return any(
            isinstance(block, ToolResultContentBlock) for block in message.content_blocks
        )

    def _summarize(self, messages: list[ChatMessage]) -> str:
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
            return ""

    @staticmethod
    def _parse_structured_summary(
        text: str,
    ) -> tuple[StructuredCompactionSummary | None, str]:
        candidate = text.strip()
        if candidate.startswith("```json"):
            candidate = candidate[7:]
        if candidate.startswith("```"):
            candidate = candidate[3:]
        if candidate.endswith("```"):
            candidate = candidate[:-3]
        try:
            data = json.loads(candidate.strip())
            summary = StructuredCompactionSummary.model_validate(data)
        except (json.JSONDecodeError, ValidationError, TypeError):
            return None, "invalid_summary_schema"
        if summary.schema_version != 1:
            return None, "unsupported_summary_schema"
        return summary, ""

    @staticmethod
    def _repair_structured_entities(
        summary: StructuredCompactionSummary, entities: list[str]
    ) -> str:
        existing = json.dumps(summary.model_dump(), ensure_ascii=False)
        missing = [item for item in entities if item not in existing]
        summary.evidence = list(dict.fromkeys([*summary.evidence, *missing]))
        return json.dumps(summary.model_dump(), ensure_ascii=False, sort_keys=True)

    @staticmethod
    def _repair_plain_entities(text: str, entities: list[str]) -> str:
        missing = [item for item in entities if item not in text]
        if not missing:
            return text.strip()
        return text.strip() + "\n保留实体：" + "、".join(missing)

    @staticmethod
    def _extract_entities(messages: list[ChatMessage]) -> list[str]:
        transcript = "\n".join(
            ContextCompactor._message_compaction_text(message)
            for message in messages
        )
        entities = [
            *_KEEP_RE.findall(transcript),
            *_RUN_ID_RE.findall(transcript),
            *_FILE_RE.findall(transcript),
        ]
        return list(dict.fromkeys(item.strip("`'\".,，。") for item in entities))[:100]

    @staticmethod
    def _build_l0_index(messages: list[ChatMessage]) -> str:
        content = "\n".join(
            ContextCompactor._message_compaction_text(message)
            for message in messages
        )
        refs = list(dict.fromkeys([
            *_KEEP_RE.findall(content),
            *_RUN_ID_RE.findall(content),
            *_FILE_RE.findall(content),
        ]))[:40]
        digests = [
            hashlib.sha256(message.content.encode("utf-8")).hexdigest()[:12]
            for message in messages
        ]
        references = ",".join(refs) if refs else "none"
        return (
            f"{_L0_MARKER} summaries={','.join(dict.fromkeys(digests))}; "
            f"refs={references}"
        )

    def _persist_l1_artifact(
        self, rendered_summary: str, *, structured: bool
    ) -> str:
        if self.artifact_dir is None:
            return ""
        digest = hashlib.sha256(rendered_summary.encode("utf-8")).hexdigest()[:16]
        suffix = ".json" if structured else ".txt"
        path = self.artifact_dir / f"compaction-{digest}{suffix}"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.with_suffix(path.suffix + ".tmp")
            temp.write_text(rendered_summary + "\n", encoding="utf-8")
            temp.replace(path)
        except OSError:
            return ""
        return str(path)

    @staticmethod
    def _build_transcript(messages: list[ChatMessage]) -> str:
        lines: list[str] = []
        for message in messages:
            content = ContextCompactor._message_compaction_text(message)
            if len(content) > 800:
                content = content[:800] + "…（已截断）"
            lines.append(f"{message.role}: {content}")
        return "\n".join(lines)

    @staticmethod
    def _message_compaction_text(message: ChatMessage) -> str:
        """Expose bounded native tool facts to summarization and entity repair."""
        parts = [message.content] if message.content else []
        for block in message.content_blocks:
            if isinstance(block, ToolUseContentBlock):
                payload = json.dumps(
                    block.input, ensure_ascii=False, sort_keys=True, default=str
                )
                parts.append(f"[tool_use:{block.name}] {payload[:800]}")
            elif isinstance(block, ToolResultContentBlock):
                parts.append(
                    f"[tool_result:{block.tool_use_id}] {block.content[:800]}"
                )
        return "\n".join(parts)
