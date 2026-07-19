"""对话 Agent：支持多轮上下文与工具循环"""
from __future__ import annotations

import asyncio
import json
import re
import threading
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from src.core.compactor import ContextCompactor
from src.core.context_budget import ContextBudgetManager
from src.core.engineering import (
    CompletionAuditor,
    Evidence,
    MutationRiskEscalator,
    RunJournal,
    RunJournalStore,
    SessionRecoveryManager,
    TaskIntent,
    TaskIntentClassifier,
    ToolEvidenceRecorder,
    VerificationTracker,
    file_mutation_metadata,
)
from src.core.memory import MemoryContextBuilder, MemoryStore
from src.core.native_content import (
    attach_tool_use_ids,
    native_tool_specs,
    tool_result_blocks,
)
from src.core.project_rules import ProjectRuleBundle, ProjectRuleResolver
from src.core.permission_rules import PermissionRuleEngine
from src.core.planning_council import PlanningCouncil, PlanningCouncilResult
from src.core.session import Session
from src.core.token_counter import count_messages_tokens
from src.gateway.client import GatewayClient
from src.models.schemas import (
    ApprovalMode,
    ChatMessage,
    ChatStreamEvent,
    MessageContentBlock,
    ModelConfig,
    StreamChunk,
    TaskResult,
)
from src.tools.file_tools import write_text_file
from src.tools.read_cache import build_read_cache_key, should_invalidate_read_cache
from src.tools.registry import tool_registry
from src.tools.tool_result import ToolResult
from src.tools.worker_tools import (
    COMMAND_PERMISSION_GUIDANCE,
    command_correction_exhausted,
    command_correction_limit_result,
    execute_tool_call,
    record_command_preflight_failure,
)


# 工具说明由注册表自动生成；这里保留调用规则与约束。
TOOL_RULES = """规则：
- 只能使用上面这种 Markdown 代码块调用工具，不要输出原生 JSON tool_use 或 function_call。
- 如果用户请求需要读取、写入或执行命令，请直接输出对应的工具代码块。
- 当用户要求分析、检查或审阅项目时，先调用 project_tree 获取精简结构，再调用 git_status 检查版本状态；search_project_files 必须沿用同一个项目根 path。随后只读取文档、依赖、入口、核心模块和测试文件，默认最多读取 12 个不同文件，禁止无差别读取全部文件，也不要用 run_command 跑 dir/ls 或 git status。
- 项目判断必须以工具返回的文件、检索、Git 或测试结果为证据；工具没有确认的细节标记为“待确认”，禁止把推测写成事实。
- 修改任务必须运行与风险匹配的真实验证：普通修改至少覆盖针对性测试和相邻模块回归；高风险构建还要有 integration/e2e、全量测试和 smoke 验证。缺少任何一层时必须说明“验证未闭环”，不能宣称已完成。
- 执行项目命令前先用 discover_project_commands 读取真实脚本；run_command 必须把工作目录放在 cwd 参数，禁止使用 cd &&、管道、重定向或 head。参数/权限失败后最多修正一次，仍失败就停止并报告。
- 当你说要“查看”、“读取”或“探查”某个文件时，必须在同一轮回复中立即调用 read_file 工具，不能只口头描述而不调用工具。
- 当用户要求生成、创建或编写文件/页面/代码时，**必须调用 write_file 工具输出每个文件**，禁止只在回复正文里写代码块（正文代码块不会被保存为文件）。每个文件一次 write_file，path 用有意义的文件名。
- 如果用户指定了绝对路径（如 G:\\MAO_test\\index.html），直接使用该路径；如果只给了文件夹（如 G:\\MAO_test），请在该文件夹下创建合理的文件名，例如 index.html、login.js、style.css。
- read_file / list_dir / glob_files / grep_content 都支持绝对路径。
- 需要查询网络信息时，使用 web_search 搜索或 fetch_url 抓取具体网页。
- 对于多步骤或项目类任务（如“做一个项目/系统/前后端应用”）：先用文字简要输出方案（要创建哪些文件、技术选型、目录结构），再逐步用 write_file 实现，不要急于写代码。
- 工具调用结束后必须给用户一份完整的最终答复，说明检查了什么、关键发现、建议或下一步，以及实际写入的文件；禁止以工具调用作为最后输出。
- 项目分析的最终答复必须包含“项目结构”章节，并复用 project_tree 的精简结果。
- 项目分析最终答复默认控制在 3000 个汉字以内；优先完整给出项目结构、关键发现、迁移阶段、风险和验收标准，宁可压缩细节也不能在标题、表格或列表中途结束。证据不足的细节标记为“待确认”，不要继续读取全部文件。
- 如果不需要工具，直接回复用户即可，不要编造工具调用。
"""


# 原生 tool_use 模式下的规则（工具定义由 tools= 参数提供，无需 Markdown 说明）
TOOL_RULES_NATIVE = """规则：
- 你可以通过原生工具调用（tool_use）使用提供的工具完成用户任务。
- 分析、检查或审阅项目时，先调用 project_tree，再调用 git_status；search_project_files 必须沿用同一个项目根 path。随后只读取文档、依赖、入口、核心模块和测试文件，默认最多读取 12 个不同文件，禁止无差别读取全部文件，也不要用 run_command 跑 dir/ls 或 git status。
- 项目判断必须以工具返回的文件、检索、Git 或测试结果为证据；未由工具确认的细节标记为“待确认”，禁止把推测写成事实。
- 修改任务必须运行与风险匹配的真实验证：普通修改至少覆盖针对性测试和相邻模块回归；高风险构建还要有 integration/e2e、全量测试和 smoke 验证。缺少任何一层时必须说明“验证未闭环”，不能宣称已完成。
- 执行项目命令前先调用 discover_project_commands；run_command 使用独立 cwd，禁止 cd &&、管道、重定向或 head。参数/权限失败后最多修正一次。
- 当你说要“查看”或“读取”某个文件时，必须立即调用 read_file，不能只口头描述。
- 当用户要求生成、创建或编写文件/页面/代码时，**必须调用 write_file 工具输出每个文件**，禁止只在回复正文里写代码块。
- 如果用户指定了绝对路径，直接使用该路径；如果只给了文件夹，请在该文件夹下创建合理的文件名。
- read_file / list_dir / glob_files / grep_content 都支持绝对路径。
- 需要查询网络信息时，使用 web_search 或 fetch_url。
- 对于多步骤或项目类任务：先用文字简要输出方案（要创建哪些文件、技术选型、目录结构），再逐步用 write_file 实现。
- 工具调用结束后必须给用户一份完整的最终答复，说明检查了什么、关键发现、建议或下一步，以及实际写入的文件；禁止以工具调用作为最后输出。
- 项目分析的最终答复必须包含“项目结构”章节，并复用 project_tree 的精简结果。
- 项目分析最终答复默认控制在 3000 个汉字以内；优先完整给出项目结构、关键发现、迁移阶段、风险和验收标准，宁可压缩细节也不能在标题、表格或列表中途结束。证据不足的细节标记为“待确认”，不要继续读取全部文件。
- 如果不需要工具，直接回复用户即可。
"""


COLLABORATION_DECISION_PROMPT = """你是任务复杂度判断器。请判断用户请求是否需要拆分成多个子任务，并由多个不同专长的 AI 模型协作完成。

只需要回答一个 JSON 对象，不要解释：
{"collaborate": true}
或
{"collaborate": false}

判断标准：
- 如果请求涉及“开发一个功能/系统/页面/API/前后端/多步骤实现”，回答 true。
- 如果只是闲聊、简单问答、解释概念、读取或修改单个文件，回答 false。
"""


# 明确的项目/多步骤任务关键字：命中则直接走协作，不依赖 LLM 判断（避免漏判）
_COLLABORATION_KEYWORDS = (
    "做一个项目", "做一个系统", "做一个应用", "做一个网站",
    "做一个前后端", "做一个全栈", "做一个完整",
    "开发一个项目", "开发一个系统", "开发一个应用", "开发一个网站",
    "实现一个项目", "实现一个系统", "实现一个应用",
    "前后端交互", "前后端项目", "全栈项目", "综合起来做", "综合做一个",
    "立项", "多步骤实现", "多页面",
)

_ANALYSIS_READ_FILE_LIMIT = 12
_ANALYSIS_FINAL_CHAR_LIMIT = 6000


class AgentTurnResult(BaseModel):
    """一轮对话的执行结果"""

    session_id: str
    user_message: str
    assistant_message: str
    tool_calls: list[dict[str, Any]]
    files_written: list[str]
    input_tokens: int
    output_tokens: int
    cost_usd: float
    run_id: str = ""
    engineering: dict[str, Any] = Field(default_factory=dict)


def _response_usage(response: Any) -> dict[str, int | float]:
    """Extract only serializable usage scalars from real or mocked responses."""
    input_tokens = getattr(response, "input_tokens", 0)
    output_tokens = getattr(response, "output_tokens", 0)
    cost_usd = getattr(response, "cost_usd", 0.0)
    return {
        "input_tokens": input_tokens if isinstance(input_tokens, int) else 0,
        "output_tokens": output_tokens if isinstance(output_tokens, int) else 0,
        "cost_usd": (
            float(cost_usd) if isinstance(cost_usd, (int, float)) else 0.0
        ),
    }


def _delivery_report_scope(user_input: str) -> Literal["session", "today"] | None:
    """Recognize only explicit engineering-history report requests."""
    normalized = " ".join(user_input.casefold().split())
    today_markers = (
        "今日工程报告", "今天的工程报告", "今日操作整理", "今天的操作过程",
        "总结今天的操作", "整理今天的操作",
    )
    session_markers = (
        "本会话工程报告", "本会话工程总结", "总结本会话操作", "整理本会话操作",
    )
    if any(marker in normalized for marker in today_markers):
        return "today"
    if any(marker in normalized for marker in session_markers):
        return "session"
    return None


class Agent:
    """对话 Agent"""

    def __init__(
        self,
        gateway: GatewayClient,
        session: Session,
        max_tool_iterations: int = 8,
        approval_mode: ApprovalMode | None = None,
        memory_store: MemoryStore | None = None,
        max_context_tokens: int = 32000,
        compaction_threshold: float = 0.75,
        journal_store: RunJournalStore | None = None,
        intent_classifier: TaskIntentClassifier | None = None,
        project_rule_resolver: ProjectRuleResolver | None = None,
        permission_rule_engine: PermissionRuleEngine | None = None,
    ):
        self.gateway = gateway
        self.session = session
        self.max_tool_iterations = max_tool_iterations
        self.approval_mode: ApprovalMode = approval_mode or session.approval_mode
        self.memory_store = memory_store
        self.max_context_tokens = max_context_tokens
        self.compaction_threshold = compaction_threshold
        self.context_budget_manager = ContextBudgetManager(
            default_safe_context_tokens=max_context_tokens
        )
        self._pending_permissions: dict[str, asyncio.Event] = {}
        self._permission_results: dict[str, bool] = {}
        self._native_tools_cache: list[dict[str, Any]] | None = None
        self._native_tools_computed = False
        self.journal_store = journal_store or RunJournalStore.from_output_dir(
            session.output_dir
        )
        self.intent_classifier = intent_classifier or TaskIntentClassifier()
        self.project_rule_resolver = project_rule_resolver or ProjectRuleResolver()
        self._active_project_rules = ProjectRuleBundle()
        self._configured_permission_engine = permission_rule_engine
        self._active_permission_engine = permission_rule_engine or PermissionRuleEngine()
        self.evidence_recorder = ToolEvidenceRecorder()
        self.verification_tracker = VerificationTracker()
        self.completion_auditor = CompletionAuditor()
        self.mutation_escalator = MutationRiskEscalator(self.session.output_dir)
        self._active_run_journal: RunJournal | None = None
        self.recovery_manager = SessionRecoveryManager(session, self.journal_store)
        self._active_recovery_checkpoint = None

    def _claim_recovery_checkpoint(self, journal: RunJournal) -> None:
        checkpoint = self.recovery_manager.claim_checkpoint(journal.run_id)
        self._active_recovery_checkpoint = checkpoint
        if checkpoint is None:
            return
        journal.decisions.append(
            f"[recovery] 续跑检查点来自 {checkpoint.run_id}；"
            f"未完成步骤 {len(checkpoint.unfinished_step_ids)} 个，"
            f"已完成步骤 {len(checkpoint.completed_step_ids)} 个。"
        )
        journal.metrics["recovery"] = checkpoint.model_dump()
        self.journal_store.save(journal)

    def _start_engineering_run(self, user_input: str) -> RunJournal:
        previous_intent = None
        try:
            previous = self.journal_store.latest()
            if previous is not None:
                previous_intent = previous.intent
        except Exception:
            pass
        intent = self.intent_classifier.classify(
            user_input,
            self.approval_mode,
            previous_intent=previous_intent,
        )
        journal = self.journal_store.create(
            self.session.id,
            user_input,
            self.approval_mode,
            intent=intent,
        )
        try:
            self._active_project_rules = self.project_rule_resolver.resolve(user_input)
        except Exception as exc:  # project rules must never prevent a conversation
            self._active_project_rules = ProjectRuleBundle(
                diagnostics=[f"项目规则解析失败：{exc}"]
            )
        journal.rule_context = self._active_project_rules.summary()
        if self._configured_permission_engine is not None:
            self._active_permission_engine = self._configured_permission_engine
        else:
            project_root = self._active_project_rules.project_root or None
            self._active_permission_engine = PermissionRuleEngine.load(
                project_root=project_root,
                user_config=str(Path(self.session.config_dir) / "permissions.yaml"),
                workspace=project_root or Path.cwd(),
            )
        journal.permission_context = self._active_permission_engine.summary()
        confirmed_facts = list(journal.metrics.get("confirmed_facts") or [])
        if (Path(self.session.config_dir) / "providers.yaml").is_file():
            confirmed_facts.append("provider_configured")
        journal.metrics["confirmed_facts"] = list(dict.fromkeys(confirmed_facts))
        journal.metrics["approval_mode"] = self.approval_mode
        if self._active_project_rules.sources:
            journal.decisions.append(
                f"加载 {len(self._active_project_rules.sources)} 个项目规则文件，"
                f"共 {self._active_project_rules.total_chars} 字符。"
            )
        self.journal_store.save(journal)
        self._active_run_journal = journal
        return journal

    def _finish_engineering_run(
        self,
        journal: RunJournal,
        status: Literal["completed", "failed", "blocked"],
        *,
        files_changed: list[str] | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd: float = 0.0,
        residual_risks: list[str] | None = None,
    ) -> dict[str, Any]:
        self.mutation_escalator.observe(journal, files_changed=files_changed)
        if files_changed and self._permission_allows_non_read_tools(journal.intent):
            journal.intent.write_authorized = True
        audit = self.completion_auditor.audit(journal, status)
        resolved_status = status
        resolved_risks = list(residual_risks or [])
        if status == "completed" and not audit.can_complete:
            resolved_status = "blocked"
            audit_detail = [*audit.missing_checks, *audit.failed_checks]
            resolved_risks.append(
                "验证未闭环" + (f"：{'、'.join(audit_detail)}" if audit_detail else "")
            )
        journal.finish(
            resolved_status,
            files_changed=files_changed,
            metrics={
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_usd": cost_usd,
            },
            residual_risks=resolved_risks,
        )
        self.journal_store.save(journal)
        if self._active_run_journal is journal:
            self._active_run_journal = None
        return journal.event_payload()

    @staticmethod
    def _apply_completion_audit_notice(
        content: str, engineering: dict[str, Any]
    ) -> str:
        audit = engineering.get("audit") or {}
        if engineering.get("status") != "blocked" or (
            not audit.get("missing_checks") and not audit.get("failed_checks")
        ):
            return content
        details = [
            *(audit.get("missing_checks") or []),
            *(audit.get("failed_checks") or []),
        ]
        notice = "验证未闭环，本轮结果已保留但未标记为完成"
        if details:
            notice += f"：{'、'.join(dict.fromkeys(details))}"
        if notice in content:
            return content
        return f"{content.rstrip()}\n\n{notice}。".strip()

    def _replace_latest_assistant_message(self, content: str) -> None:
        for message in reversed(self.session.messages):
            if message.role == "assistant":
                message.content = content
                return

    def _record_provider_trace(self, journal: RunJournal) -> bool:
        trace = list(getattr(self.gateway, "last_attempt_trace", []) or [])
        failures = [item for item in trace if not item.get("success")]
        if not failures:
            return False
        final = trace[-1] if trace else {}
        attempted_models = list(dict.fromkeys(
            str(item.get("model", "")) for item in trace if item.get("model")
        ))
        error_codes = list(dict.fromkeys(
            str(item.get("error_code", ""))
            for item in failures
            if item.get("error_code")
        ))
        evidence = Evidence(
            source="gateway:provider",
            claim=(
                f"Provider 请求经过 {len(trace)} 次尝试，"
                f"最终模型为 {final.get('model') or '未完成'}"
            ),
            excerpt=json.dumps(trace, ensure_ascii=False),
            confidence=1.0,
            kind="runtime",
            success=bool(final.get("success")),
            metadata={
                "attempts": len(trace),
                "failed_attempts": len(failures),
                "attempted_models": attempted_models,
                "final_model": final.get("model", ""),
                "error_codes": error_codes,
                "failover": len(attempted_models) > 1,
            },
        )
        _, added = journal.add_evidence(evidence)
        return added

    def _fail_engineering_run(
        self, journal: RunJournal, error: Exception | str
    ) -> dict[str, Any]:
        if journal.status != "running":
            return journal.event_payload()
        self._record_provider_trace(journal)
        message = str(error)
        journal.decisions.append(f"运行异常：{message}")
        return self._finish_engineering_run(
            journal,
            "failed",
            residual_risks=[message],
        )

    def _record_tool_evidence(
        self,
        journal: RunJournal,
        tool_name: str,
        params: dict[str, Any],
        result: ToolResult,
        *,
        cached: bool = False,
        skipped: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """记录真实工具结果；有状态变化时立即原子持久化。"""
        evidence_changed = self.evidence_recorder.record(
            journal,
            tool_name,
            params,
            result,
            cached=cached,
            skipped=skipped,
            metadata=metadata,
        )
        verification_changed = self.verification_tracker.record(
            journal,
            tool_name,
            params,
            result,
            cached=cached,
            skipped=skipped,
        )
        mutation_changed = self.mutation_escalator.observe(journal)
        changed = evidence_changed or verification_changed or mutation_changed
        if changed:
            self.journal_store.save(journal)
        return changed

    def _provider_type(self) -> str:
        """获取主模型的 provider 类型（anthropic/openai/ollama/llamacpp）"""
        main = self.gateway.main_model
        if not main:
            return ""
        try:
            cfg = self.gateway.get_model_config(main)
            prov = self.gateway.providers.get(cfg.provider)
            return prov.config.type if prov else ""
        except Exception:
            return ""

    def _should_use_native_tools(self) -> bool:
        """是否启用原生 tool_use：优先 native_tools 配置，否则按 capabilities 自动判断"""
        main = self.gateway.main_model
        if not main:
            return False
        try:
            cfg = self.gateway.get_model_config(main)
        except Exception:
            return False
        if not isinstance(cfg, ModelConfig):
            return False
        if cfg.native_tools is not None:
            return cfg.native_tools
        return cfg.supports_capability("tool_use")

    def _get_native_tools(self) -> list[dict[str, Any]] | None:
        """获取原生工具 schema（缓存）。不启用原生时返回 None"""
        if not self._native_tools_computed:
            if self._should_use_native_tools():
                ptype = self._provider_type()
                schema_type = "anthropic" if ptype == "anthropic" else "openai"
                self._native_tools_cache = tool_registry.build_tool_schemas(schema_type)
            else:
                self._native_tools_cache = None
            self._native_tools_computed = True
        return self._native_tools_cache

    def _native_kwargs(self, read_only: bool = False) -> dict[str, Any]:
        """构造传给 gateway 的工具相关 kwargs"""
        if read_only and self._should_use_native_tools():
            names = []
            for name in tool_registry.list_tools():
                spec = tool_registry.get(name)
                if spec and spec.category == "read":
                    names.append(name)
            ptype = self._provider_type()
            schema_type = "anthropic" if ptype == "anthropic" else "openai"
            tools = tool_registry.build_tool_schemas(schema_type, names)
        else:
            tools = self._get_native_tools()
        return {"tools": tools} if tools else {}

    def _get_effective_max_context(self) -> int:
        """Return the current model's safe input budget for compaction."""
        main_model = self.gateway.main_model
        if main_model:
            try:
                cfg = self.gateway.get_model_config(main_model)
                budget = self.context_budget_manager.calculate(
                    main_model,
                    cfg,
                    self.session.messages,
                    requested_output_tokens=cfg.max_output_tokens,
                    tools=self._get_native_tools(),
                )
                return budget.input_budget_tokens
            except Exception:
                pass
        return self.max_context_tokens

    def get_context_status(self) -> dict[str, Any]:
        """返回无需模型推测的上下文预算与压缩状态。"""
        main_model = getattr(self.gateway, "main_model", None)
        if not isinstance(main_model, str):
            main_model = ""

        provider = ""
        model_id = ""
        cfg = None
        if main_model:
            try:
                cfg = self.gateway.get_model_config(main_model)
                provider = cfg.provider
                model_id = cfg.model_id
            except Exception:
                cfg = None

        if cfg is None:
            cfg = ModelConfig(provider=provider or "unknown", model_id=model_id or "unknown")
        budget = self.context_budget_manager.calculate(
            main_model or "unknown",
            cfg,
            self.session.messages,
            requested_output_tokens=cfg.max_output_tokens,
            tools=self._get_native_tools(),
        )
        status = budget.to_dict()
        status.update({
            "model_alias": main_model or "unknown",
            "provider": provider or "unknown",
            "model_id": model_id or "unknown",
            # Compatibility keys for existing CLI/Web consumers.
            "max_context_tokens": budget.safe_context_tokens,
            "max_context_source": (
                "model_config"
                if cfg.context_window_tokens > 0 or cfg.max_context_tokens > 0
                else "agent_default"
            ),
            "current_tokens": budget.current_input_tokens,
            "compaction_enabled": budget.input_budget_tokens > 0,
            "compaction_limit_tokens": budget.compaction_trigger_tokens,
            "compaction_count": len(self.session.compaction_events),
            "recent_compactions": self.session.compaction_events[-3:],
            "usage_observations": [
                {
                    **obs,
                    "error_pct": round(
                        (obs["actual_input"] - obs["estimated_input"])
                        / obs["actual_input"]
                        * 100,
                        1,
                    ),
                }
                for obs in self.session.usage_observations[-3:]
                if obs.get("actual_input")
            ],
        })
        return status

    def _runtime_facts_prompt(self) -> str:
        """把稳定的运行参数告诉模型，避免把协议类型误认为模型身份。"""
        status = self.get_context_status()
        source = status["context_window_source"]
        enabled = "已启用" if status["compaction_enabled"] else "未启用"
        return (
            "【MAO 运行时事实】\n"
            f"- 当前主模型别名：{status['model_alias']}；Provider：{status['provider']}；"
            f"上游请求模型 ID：{status['model_id']}。\n"
            f"- 上游硬窗口：{status['context_window_tokens'] or '未知'} tokens（{source}）；"
            f"MAO 安全输入预算：{status['input_budget_tokens']} tokens；"
            f"自动压缩：{enabled}；触发阈值约 {status['compaction_limit_tokens']} tokens "
            f"（{status['compaction_threshold']:.0%}）。\n"
            "- Provider 类型 anthropic 仅表示 API 兼容协议，不表示当前模型是 Claude。\n"
            "用户询问模型、上下文或自动压缩时，必须依据以上运行时事实回答，不得猜测其他模型配置。"
        )

    def _maybe_compact_context(self) -> bool:
        """超阈值时压缩旧消息，返回是否执行了压缩"""
        max_ctx = self._get_effective_max_context()
        if max_ctx <= 0:
            return False
        compactor = ContextCompactor(
            self.gateway,
            max_context_tokens=max_ctx,
            threshold=self.get_context_status()["compaction_threshold"],
            artifact_dir=Path(self.session.output_dir) / "context",
            task_checkpoint=self._build_task_checkpoint(),
        )
        if not compactor.needs_compaction(self.session.messages):
            return False
        before = len(self.session.messages)
        new_messages = compactor.maybe_compact(self.session.messages)
        if len(new_messages) < before:
            metadata = compactor.last_metadata
            self.session.record_compaction_event(
                {
                    "at": datetime.now(timezone.utc).isoformat(),
                    "before_tokens": count_messages_tokens(self.session.messages),
                    "after_tokens": count_messages_tokens(new_messages),
                    "dropped_messages": before - len(new_messages),
                    "layer": "/".join(metadata.layers),
                    "layers": metadata.layers,
                    "deduplicated_messages": metadata.deduplicated_messages,
                    "schema_valid": metadata.schema_valid,
                    "fallback_used": metadata.fallback_used,
                    "fallback_reason": metadata.fallback_reason,
                    "entity_retention": metadata.entity_retention,
                    "task_relevance_ratio": metadata.task_relevance_ratio,
                    "quality_passed": metadata.quality_passed,
                    "checkpoint_count": metadata.checkpoint_count,
                    "artifact_path": metadata.artifact_path,
                }
            )
            self.session.messages = new_messages
            return True
        return False

    def _build_task_checkpoint(self) -> str:
        """Build a bounded deterministic checkpoint that summaries cannot absorb."""
        journal = self._active_run_journal
        if journal is None:
            return ""
        pending_steps = []
        completed_steps = []
        if journal.plan is not None:
            pending_steps = [
                {"id": step.id, "title": step.title, "status": step.status}
                for step in journal.plan.steps
                if step.status != "completed"
            ]
            completed_steps = [step.id for step in journal.plan.steps if step.status == "completed"]
        checkpoint = {
            "run_id": journal.run_id,
            "objective": journal.objective,
            "pending_steps": pending_steps[:30],
            "completed_step_ids": completed_steps[:30],
            "evidence_ids": [item.id for item in journal.evidence[-30:]],
            "files_changed": journal.files_changed[-30:],
            "residual_risks": journal.residual_risks[-20:],
        }
        return json.dumps(checkpoint, ensure_ascii=False, sort_keys=True)[:8000]

    def _record_usage_observation(self, actual_input_tokens: int) -> None:
        """Provider 返回真实 usage 时，记录本地 token 估算的误差（有界）。"""
        if actual_input_tokens <= 0:
            return
        estimated = count_messages_tokens(self.session.messages)
        if estimated <= 0:
            return
        self.session.record_usage_observation(
            {
                "at": datetime.now(timezone.utc).isoformat(),
                "estimated_input": estimated,
                "actual_input": actual_input_tokens,
            }
        )

    @staticmethod
    def _task_policy_prompt(intent: TaskIntent) -> str:
        if intent.policy.allow_project_writes:
            access = "任务允许按会话权限模式申请项目写入"
        elif intent.policy.permission_follows_session:
            access = "任务未明确分类，工具权限跟随会话模式和用户当前请求"
        else:
            access = "仅允许只读工具，禁止项目写入和命令执行"
        authorization = (
            "已授权"
            if intent.write_authorized
            else "未授权；如任务允许写入，仍须遵循 approve/readonly 边界"
        )
        return (
            "【本轮任务策略】\n"
            f"- 类型：{intent.kind}；风险：{intent.risk_level}；{access}。\n"
            f"- 写入授权：{authorization}；验证深度：{intent.policy.verification_depth}；"
            f"需要计划：{'是' if intent.policy.requires_plan else '否'}。\n"
            "必须遵守该策略；只读任务即使用户会话处于 auto 模式，也不得调用写入或命令工具。"
        )

    def _plan_mode_prompt(self) -> str:
        if self.session.plan_mode == "inactive":
            return ""
        artifact = self.session.plan_artifact
        objective = artifact.objective if artifact else ""
        feedback = artifact.feedback if artifact else ""
        lines = [
            "【Plan 模式强制边界】",
            f"当前状态：{self.session.plan_mode}。",
            "本轮只能侦察、分析和制定方案；禁止修改项目、执行可能写入的命令、调用写入型 MCP 或派发写入型 Worker。",
            "项目规则不能放宽此边界。请输出可审阅的实施步骤、风险、验证方式和验收标准，不要实施。",
        ]
        if objective:
            lines.append(f"规划目标：{objective}")
        if feedback:
            lines.append(f"用户修订意见：{feedback}")
        return "\n".join(lines)

    def _plan_mode_is_read_only(self) -> bool:
        return self.session.plan_mode != "inactive"

    def _recovery_checkpoint_prompt(self) -> str:
        checkpoint = self._active_recovery_checkpoint
        if checkpoint is None:
            return ""
        unfinished = "、".join(checkpoint.unfinished_step_titles) or "无结构化步骤"
        completed = "、".join(checkpoint.completed_step_titles) or "无"
        files = "、".join(checkpoint.files_changed[:30]) or "无"
        return "\n".join([
            "【中断任务恢复检查点】",
            f"来源 run：{checkpoint.run_id}。",
            f"仅处理未完成步骤：{unfinished}。",
            f"已完成步骤：{completed}。不得自动重放这些步骤。",
            f"既有变更文件：{files}。写入前先检查现状，禁止仅为重放而重复生成。",
            "本次续跑必须创建新的工程 run；旧 run 和直接证据保持只读。",
        ])

    def _refine_plan(
        self, user_input: str, draft: str, run_journal: RunJournal
    ) -> PlanningCouncilResult:
        evidence = "\n".join(
            f"- {item.claim}: {item.excerpt or item.path or item.command}"
            for item in run_journal.evidence[-20:]
        )
        council = PlanningCouncil(
            self.gateway,
            project_rules=self._active_project_rules.prompt(),
            permission_context=self._active_permission_engine.summary(),
        )
        return council.refine(user_input, draft, evidence)

    @staticmethod
    def _permission_allows_non_read_tools(intent: TaskIntent) -> bool:
        """Separate tool capability from engineering-change verification policy."""
        return bool(
            intent.policy.allow_project_writes
            or intent.policy.permission_follows_session
        )

    def _build_system_prompt(
        self,
        user_input: str = "",
        intent: TaskIntent | None = None,
    ) -> str:
        """构建系统提示，包含工具说明和相关记忆上下文"""
        native = self._should_use_native_tools()
        parts = [
            "你是 Multi-Agent Orchestrator 的会话助手，可以与用户进行多轮对话，并使用本地工具帮助用户完成任务。",
            self._runtime_facts_prompt(),
        ]
        if intent is not None:
            parts.append(self._task_policy_prompt(intent))
        plan_prompt = self._plan_mode_prompt()
        if plan_prompt:
            parts.append(plan_prompt)
        recovery_prompt = self._recovery_checkpoint_prompt()
        if recovery_prompt:
            parts.append(recovery_prompt)
        if native:
            # 原生模式：工具定义由 tools= 参数提供，系统提示不再列 Markdown 工具块
            parts.append(TOOL_RULES_NATIVE)
        else:
            parts.append("")
            parts.append(tool_registry.build_instructions())
            parts.append(TOOL_RULES)
        if self.memory_store and self.memory_store.config.enabled:
            builder = MemoryContextBuilder(self.memory_store)
            memory_context = builder.build_context(user_input)
            if memory_context:
                parts.append(memory_context)
        project_rules = self._active_project_rules.prompt()
        if project_rules:
            parts.append(project_rules)
        return "\n\n".join(parts)

    def _ensure_system_prompt(
        self,
        user_input: str = "",
        intent: TaskIntent | None = None,
    ) -> None:
        """确保消息列表第一条是系统提示"""
        content = self._build_system_prompt(user_input, intent)
        if not self.session.messages or self.session.messages[0].role != "system":
            self.session.messages.insert(0, ChatMessage(role="system", content=content))
        else:
            self.session.messages[0].content = content

    @staticmethod
    def _parse_tool_calls(content: str) -> list[dict[str, Any]]:
        """解析 assistant 回复中的工具调用块。

        兼容两种闭合方式：
        1. 标准 Markdown：```tool:xxx\\n{...}```
        2. 部分编码模型（如 ark-coding / kimi-for-coding）使用特殊 token：
           ```tool:xxx\\n{...}<|tool_calls_section_end|>
        """
        # 闭合标记：三反引号、特殊 token，或字符串结尾
        pattern = r"```tool:(\w+)\n(.*?)(?:```|<\|tool_calls_section_end\|>|$)"
        calls: list[dict[str, Any]] = []
        for match in re.finditer(pattern, content, re.DOTALL):
            tool_name = match.group(1)
            raw = match.group(2).strip()
            # 去掉残留的特殊 token
            raw = raw.replace("<|tool_calls_section_end|>", "").strip()
            try:
                params = json.loads(raw)
            except json.JSONDecodeError as e:
                calls.append({"tool": tool_name, "params": {}, "parse_error": str(e)})
                continue
            calls.append({"tool": tool_name, "params": params})
        return calls

    @classmethod
    def _tool_specs(
        cls, content: str, content_blocks: list[MessageContentBlock] | None = None
    ) -> list[dict[str, Any]]:
        native_specs = native_tool_specs(content_blocks or [])
        return native_specs or cls._parse_tool_calls(content)

    @staticmethod
    def _strip_toolcall_artifacts(content: str) -> str:
        """清除编码模型遗留的特殊 token，避免污染展示与上下文"""
        cleaned = content.replace("<|tool_calls_section_start|>", "")
        cleaned = cleaned.replace("<|tool_calls_section_end|>", "")
        return cleaned

    @staticmethod
    def _format_tool_result(tool_name: str, result: ToolResult) -> str:
        status = "成功" if result.success else "失败"
        lines = [f"\n[工具 {tool_name} 执行{status}]"]
        if result.success:
            lines.append(result.output or "（无输出）")
        else:
            lines.append(result.error or "未知错误")
        lines.append("[工具结果结束]\n")
        return "\n".join(lines)

    @staticmethod
    def _build_permission_message(tool_name: str, params: dict[str, Any]) -> str:
        """生成人类可读的工具调用确认信息，对任意工具通用"""
        # 优先展示语义关键字段
        key_labels = [
            ("path", "路径"),
            ("command", "命令"),
            ("url", "URL"),
            ("query", "查询"),
        ]
        details = []
        for key, label in key_labels:
            value = params.get(key)
            if value:
                details.append(f"{label}：{value}")
        if details:
            return f"请求执行工具 {tool_name}（{'，'.join(details)}）"
        # 兜底：展示所有参数
        if params:
            summary = ", ".join(f"{k}={v}" for k, v in params.items())
            return f"请求执行工具 {tool_name}（{summary}）"
        return f"请求执行工具：{tool_name}"

    @staticmethod
    def _record_written_file(
        tool_name: str, params: dict[str, Any], result: ToolResult, files_written: list[str]
    ) -> None:
        """如果工具成功写入了文件，记录到 files_written 列表"""
        if tool_name == "write_file" and result.success:
            path = params.get("path")
            if path and path not in files_written:
                files_written.append(path)

    @staticmethod
    def _handle_stream_chunk(chunk: StreamChunk) -> ChatStreamEvent | None:
        """把 Gateway 的 StreamChunk 转成 ChatStreamEvent；返回 None 表示不对外发事件"""
        if chunk.type == "delta":
            return ChatStreamEvent(type="delta", delta=chunk.content or "")
        if chunk.type == "usage":
            return None
        if chunk.type == "failover":
            return ChatStreamEvent(
                type="model_failover",
                delta=f"⚠ 模型 {chunk.from_model} 连接失效，已切换到 {chunk.to_model}",
                failover={
                    "from_model": chunk.from_model or "",
                    "to_model": chunk.to_model or "",
                    "reason": chunk.reason or "",
                    "error_code": chunk.error_code or "",
                    "attempts": chunk.attempts,
                },
            )
        return None

    def _execute_tool_calls(
        self,
        content: str,
        content_blocks: list[MessageContentBlock] | None = None,
        files_written: list[str] | None = None,
        read_cache: dict[str, ToolResult] | None = None,
        analysis_only: bool = False,
        read_file_keys: set[str] | None = None,
        run_journal: RunJournal | None = None,
    ) -> tuple[str, list[dict[str, Any]]]:
        """同步执行工具调用；approve 无法交互确认时拒绝非只读工具。"""
        calls: list[dict[str, Any]] = []
        outputs: list[str] = []

        specs = self._tool_specs(content, content_blocks)
        for spec in specs:
            tool_name = spec["tool"]
            params = spec.get("params", {})

            if (
                tool_name == "run_command"
                and run_journal is not None
                and command_correction_exhausted(run_journal.metrics)
            ):
                result = command_correction_limit_result(str(params.get("cwd", ".")))
                calls.append({
                    "tool": tool_name,
                    "params": params,
                    "success": False,
                    "output": result.output,
                    "error": result.error,
                    "cached": False,
                    "metadata": result.metadata,
                })
                outputs.append(self._format_tool_result(tool_name, result))
                continue

            cache_key = build_read_cache_key(tool_name, params, self.session.output_dir)
            tool_spec = tool_registry.get(tool_name)
            category = tool_spec.category if tool_spec else "unknown"
            decision = self._active_permission_engine.decide(
                tool_name,
                params,
                category=category,
                approval_mode=self.approval_mode,
                hard_read_only=analysis_only,
            )

            if decision.action == "deny":
                denial_reason = decision.reason
                if tool_name == "run_command":
                    denial_reason = f"{denial_reason}；{COMMAND_PERMISSION_GUIDANCE}"
                calls.append({
                    "tool": tool_name,
                    "params": params,
                    "success": False,
                    "error": f"权限规则拒绝：{denial_reason}",
                    "permission": decision.summary(),
                    "metadata": {"error_code": "permission_denied"},
                })
                if tool_name == "run_command" and run_journal is not None:
                    record_command_preflight_failure(
                        run_journal.metrics, {"error_code": "permission_denied"}
                    )
                    self.journal_store.save(run_journal)
                outputs.append(f"\n[工具 {tool_name} 被拒绝：{denial_reason}]\n")
                continue

            if decision.action == "ask":
                ask_error = "权限规则要求确认；同步执行无法交互确认，工具已拒绝"
                if tool_name == "run_command":
                    ask_error = f"{ask_error}；{COMMAND_PERMISSION_GUIDANCE}"
                call = {
                    "tool": tool_name,
                    "params": params,
                    "success": False,
                    "error": ask_error,
                    "permission": decision.summary(),
                    "metadata": {"error_code": "permission_denied"},
                }
                if tool_name == "run_command" and run_journal is not None:
                    record_command_preflight_failure(
                        run_journal.metrics, {"error_code": "permission_denied"}
                    )
                    self.journal_store.save(run_journal)
                calls.append(call)
                outputs.append(
                    f"\n[工具 {tool_name} 被拒绝：请使用流式对话完成权限确认]\n"
                )
                continue
            if (
                analysis_only
                and tool_name == "read_file"
                and read_file_keys is not None
                and (read_cache is None or cache_key not in read_cache)
                and cache_key not in read_file_keys
                and len(read_file_keys) >= _ANALYSIS_READ_FILE_LIMIT
            ):
                error = f"项目分析抽样已达到 {_ANALYSIS_READ_FILE_LIMIT} 个不同文件上限"
                result = ToolResult(success=True, output=error)
                calls.append({
                    "tool": tool_name,
                    "params": params,
                    "success": True,
                    "output": error,
                    "error": None,
                    "cached": False,
                    "skipped": True,
                })
                outputs.append(self._format_tool_result(tool_name, result))
                if run_journal is not None:
                    self._record_tool_evidence(
                        run_journal, tool_name, params, result, skipped=True
                    )
                continue
            if analysis_only and tool_name == "read_file" and cache_key and read_file_keys is not None:
                read_file_keys.add(cache_key)
            cached = bool(read_cache is not None and cache_key in read_cache)
            mutation_metadata = file_mutation_metadata(
                tool_name, params, self.session.output_dir
            )
            if cached:
                result = read_cache[cache_key]  # type: ignore[index]
            else:
                result = execute_tool_call(tool_name, params, self.session.output_dir)
                if read_cache is not None and cache_key and result.success:
                    read_cache[cache_key] = result
                if read_cache is not None and should_invalidate_read_cache(tool_name):
                    read_cache.clear()
            cached = cached or bool(result.metadata.get("cached"))
            calls.append({
                "tool": tool_name,
                "params": params,
                "success": result.success,
                "output": result.output,
                "error": result.error,
                "cached": cached,
                "mutation_metadata": mutation_metadata,
                "metadata": result.metadata,
                "permission": decision.summary(),
            })
            if tool_name == "run_command" and not result.success and run_journal is not None:
                record_command_preflight_failure(run_journal.metrics, result.metadata)
            outputs.append(self._format_tool_result(tool_name, result))
            if run_journal is not None:
                self._record_tool_evidence(
                    run_journal,
                    tool_name,
                    params,
                    result,
                    cached=cached,
                    metadata={
                        "permission": decision.summary(),
                        **mutation_metadata,
                    },
                )
            if files_written is not None:
                self._record_written_file(tool_name, params, result, files_written)

        attach_tool_use_ids(calls, specs)
        return "\n".join(outputs), calls

    def _register_permission_request(self) -> str:
        """注册一个新的权限请求，返回 request_id"""
        request_id = f"perm-{self.session.id}-{uuid.uuid4().hex[:8]}"
        self._pending_permissions[request_id] = asyncio.Event()
        self._permission_results[request_id] = False
        return request_id

    def respond_to_permission(self, request_id: str, approved: bool) -> bool:
        """Resolve one live permission request without retaining stale IDs."""
        event = self._pending_permissions.get(request_id)
        if event is None:
            return False
        self._permission_results[request_id] = approved
        if not event.is_set():
            event.set()
        return True

    async def _wait_for_permission(self, request_id: str) -> bool:
        """等待用户对指定权限请求的响应"""
        event = self._pending_permissions.get(request_id)
        if not event:
            return False
        try:
            await event.wait()
            return self._permission_results.get(request_id, False)
        finally:
            self._pending_permissions.pop(request_id, None)
            self._permission_results.pop(request_id, None)

    def _has_tool_calls(
        self, content: str, content_blocks: list[MessageContentBlock] | None = None
    ) -> bool:
        return bool(native_tool_specs(content_blocks or [])) or bool(
            re.search(r"```tool:\w+\n", content, re.DOTALL)
        )

    def run_turn(self, user_input: str) -> AgentTurnResult:
        """执行一轮对话"""
        self.recovery_manager.require_ready()
        run_journal = self._start_engineering_run(user_input)
        self._claim_recovery_checkpoint(run_journal)

        try:
            if self.session.plan_mode == "pending":
                self.session.activate_plan_mode()
            self._ensure_system_prompt(user_input, run_journal.intent)
            self.session.add_message("user", user_input)
            report_scope = _delivery_report_scope(user_input)
            if report_scope:
                content = self._build_local_delivery_report(
                    report_scope, exclude_run_id=run_journal.run_id
                )
                self.session.add_message("assistant", content)
                engineering = self._finish_engineering_run(run_journal, "completed")
                return AgentTurnResult(
                    session_id=self.session.id,
                    user_message=user_input,
                    assistant_message=content,
                    tool_calls=[],
                    files_written=[],
                    input_tokens=0,
                    output_tokens=0,
                    cost_usd=0.0,
                    run_id=run_journal.run_id,
                    engineering=engineering,
                )
            self._maybe_compact_context()
            return self._run_turn_impl(user_input, run_journal)
        except Exception as exc:
            self._fail_engineering_run(run_journal, exc)
            raise

    def _run_turn_impl(
        self, user_input: str, run_journal: RunJournal
    ) -> AgentTurnResult:
        """已建立 RunJournal 后执行同步工具循环。"""

        total_input = 0
        total_output = 0
        total_cost = 0.0
        tool_calls: list[dict[str, Any]] = []
        files_written: list[str] = []
        final_content = ""
        read_cache: dict[str, ToolResult] = {}
        analysis_only = (
            not self._permission_allows_non_read_tools(run_journal.intent)
            or self.approval_mode == "readonly"
            or self._plan_mode_is_read_only()
        )
        read_file_keys: set[str] = set()

        iterations = 0
        while True:
            self._maybe_compact_context()
            response = self.gateway.chat_with_main_model(
                messages=self.session.messages,
                task_id=f"chat-{self.session.id}",
                max_tokens=4096,
                temperature=0.2,
                **self._native_kwargs(read_only=analysis_only),
            )
            self._record_provider_trace(run_journal)
            total_input += response.input_tokens
            total_output += response.output_tokens
            total_cost += response.cost_usd
            self._record_usage_observation(response.input_tokens)

            # 空响应守卫：首轮无文本且无工具调用时按失败处理，避免假完成；
            # 工具轮之后的空响应保持原有收尾行为
            if (
                iterations == 0
                and not response.content.strip()
                and not self._has_tool_calls(response.content, response.content_blocks)
            ):
                engineering = self._finish_engineering_run(
                    run_journal,
                    "failed",
                    input_tokens=total_input,
                    output_tokens=total_output,
                    cost_usd=total_cost,
                    residual_risks=["模型无响应或返回空内容"],
                )
                return AgentTurnResult(
                    session_id=self.session.id,
                    user_message=user_input,
                    assistant_message=(
                        "模型无响应或返回空内容。请检查 Provider 连接与模型 ID 是否正确，"
                        "或换一个模型重试。"
                    ),
                    tool_calls=tool_calls,
                    files_written=files_written,
                    input_tokens=total_input,
                    output_tokens=total_output,
                    cost_usd=total_cost,
                    run_id=run_journal.run_id,
                    engineering=engineering,
                )

            self.session.add_message(
                "assistant",
                response.content,
                response.content_blocks,
                response.provider_payload,
            )
            final_content = response.content

            if not self._has_tool_calls(response.content, response.content_blocks):
                break
            if iterations >= self.max_tool_iterations:
                # 达到最大工具轮数，追加提示并要求模型直接给出最终结果
                limit_specs = self._tool_specs(
                    response.content, response.content_blocks
                )
                limit_calls = [
                    {
                        "tool": spec["tool"],
                        "params": spec.get("params", {}),
                        "success": False,
                        "error": "已达到最大工具调用次数",
                    }
                    for spec in limit_specs
                ]
                attach_tool_use_ids(limit_calls, limit_specs)
                tool_calls.extend(limit_calls)
                limit_prompt = "已达到最大工具调用次数，请基于已获得的信息直接完成用户请求，不要再调用工具。"
                self.session.add_message(
                    "user",
                    limit_prompt,
                    tool_result_blocks(limit_calls, limit_prompt),
                )
                response = self.gateway.chat_with_main_model(
                    messages=self.session.messages,
                    task_id=f"chat-{self.session.id}-finalize",
                    max_tokens=4096,
                    temperature=0.2,
                    **self._native_kwargs(read_only=analysis_only),
                )
                self._record_provider_trace(run_journal)
                total_input += response.input_tokens
                total_output += response.output_tokens
                total_cost += response.cost_usd
                self._record_usage_observation(response.input_tokens)
                self.session.add_message(
                    "assistant",
                    response.content,
                    response.content_blocks,
                    response.provider_payload,
                )
                final_content = response.content
                break

            tool_results_text, calls = self._execute_tool_calls(
                response.content,
                response.content_blocks,
                files_written,
                read_cache,
                analysis_only,
                read_file_keys,
                run_journal,
            )
            if not calls:
                break

            tool_calls.extend(calls)
            self.session.add_message(
                "user",
                tool_results_text + "\n\n请继续完成用户请求。",
                tool_result_blocks(calls),
            )
            iterations += 1

        if analysis_only and len(final_content) > _ANALYSIS_FINAL_CHAR_LIMIT:
            self.session.add_message(
                "user",
                "上一版答复过长。请基于已经获得的证据，重新输出一份不超过 3000 个汉字的完整答复。"
                "保留用户要求、关键结论、证据、风险和下一步；不要调用任何工具，"
                "不要在标题、表格或列表中途结束。只输出最终答复。",
            )
            response = self.gateway.chat_with_main_model(
                messages=self.session.messages,
                task_id=f"chat-{self.session.id}-concise",
                max_tokens=4096,
                temperature=0.2,
            )
            self._record_provider_trace(run_journal)
            total_input += response.input_tokens
            total_output += response.output_tokens
            total_cost += response.cost_usd
            self._record_usage_observation(response.input_tokens)
            concise_content = self._strip_toolcall_artifacts(response.content).strip()
            if concise_content:
                final_content = concise_content
                self.session.add_message(
                    "assistant",
                    final_content,
                    response.content_blocks,
                    response.provider_payload,
                )

        # 不再自动抽取代码块为 generated_N 文件（易产出无意义文件名）；
        # 模型应通过 write_file 显式写文件。仅当本轮未写任何文件时，兜底保存回复为 response.md。
        if (
            self.approval_mode == "auto"
            and not self._plan_mode_is_read_only()
            and not files_written
            and final_content.strip()
        ):
            files_written.append(write_text_file("response.md", final_content, self.session.output_dir))

        if self.session.plan_mode in ("pending", "active") and final_content.strip():
            council_result = self._refine_plan(user_input, final_content, run_journal)
            final_content = council_result.content
            total_input += council_result.input_tokens
            total_output += council_result.output_tokens
            total_cost += council_result.cost_usd
            self._replace_latest_assistant_message(final_content)
            self.session.save_plan_artifact(
                final_content, council=council_result.summary()
            )

        engineering = self._finish_engineering_run(
            run_journal,
            "completed",
            files_changed=files_written,
            input_tokens=total_input,
            output_tokens=total_output,
            cost_usd=total_cost,
        )
        final_content = self._apply_completion_audit_notice(final_content, engineering)
        self._replace_latest_assistant_message(final_content)

        return AgentTurnResult(
            session_id=self.session.id,
            user_message=user_input,
            assistant_message=final_content,
            tool_calls=tool_calls,
            files_written=files_written,
            input_tokens=total_input,
            output_tokens=total_output,
            cost_usd=total_cost,
            run_id=run_journal.run_id,
            engineering=engineering,
        )

    async def run_turn_stream(
        self,
        user_input: str,
    ) -> AsyncIterator[ChatStreamEvent]:
        """流式执行一轮对话，按 delta/done 事件产出"""
        await asyncio.to_thread(self.recovery_manager.require_ready)
        run_journal = await asyncio.to_thread(self._start_engineering_run, user_input)
        await asyncio.to_thread(self._claim_recovery_checkpoint, run_journal)
        yield ChatStreamEvent(
            type="engineering_start",
            engineering=run_journal.event_payload(),
        )

        try:
            if self.session.plan_mode == "pending":
                self.session.activate_plan_mode()
            self._ensure_system_prompt(user_input, run_journal.intent)
            self.session.add_message("user", user_input)
            report_scope = _delivery_report_scope(user_input)
            if report_scope:
                content = await asyncio.to_thread(
                    self._build_local_delivery_report,
                    report_scope,
                    exclude_run_id=run_journal.run_id,
                )
                self.session.add_message("assistant", content)
                engineering = await asyncio.to_thread(
                    self._finish_engineering_run, run_journal, "completed"
                )
                yield ChatStreamEvent(type="delta", delta=content)
                yield ChatStreamEvent(
                    type="engineering_complete", engineering=engineering
                )
                yield ChatStreamEvent(
                    type="done",
                    assistant_message=content,
                    input_tokens=0,
                    output_tokens=0,
                    cost_usd=0.0,
                )
                return
            await asyncio.to_thread(self._maybe_compact_context)
            async for event in self._run_turn_stream_impl(user_input, run_journal):
                yield event
        except Exception as exc:
            engineering = await asyncio.to_thread(
                self._fail_engineering_run, run_journal, exc
            )
            yield ChatStreamEvent(
                type="engineering_complete",
                engineering=engineering,
            )
            raise

    def _build_local_delivery_report(
        self,
        scope: Literal["session", "today"],
        *,
        exclude_run_id: str,
    ) -> str:
        from src.core.engineering import DeliveryReportBuilder, load_today_journals

        if scope == "today":
            sessions_root = Path(self.session.output_dir).resolve().parent.parent
            journals = load_today_journals(sessions_root)
            report = DeliveryReportBuilder().build(
                (item for item in journals if item.run_id != exclude_run_id),
                scope="today",
            )
        else:
            journals = self.journal_store.list()
            report = DeliveryReportBuilder().build(
                (item for item in journals if item.run_id != exclude_run_id),
                scope="session",
                session_id=self.session.id,
            )
        return report.to_markdown()

    async def _run_turn_stream_impl(
        self,
        user_input: str,
        run_journal: RunJournal,
    ) -> AsyncIterator[ChatStreamEvent]:
        """已建立 RunJournal 后执行流式工具循环。"""
        billing_before = self.gateway.billing.summary()

        # 自动判断是否需要多模型协作（只读模式下不走协作，避免自动写文件）
        if (
            self.approval_mode != "readonly"
            and not self._plan_mode_is_read_only()
            and run_journal.intent.policy.collaboration_allowed
            and await self._should_collaborate(user_input, run_journal.intent)
        ):
            async for event in self._run_collaboration_stream(
                user_input, billing_before, run_journal
            ):
                if event.type == "done":
                    run_status = (
                        "blocked" if "取消" in event.assistant_message else "completed"
                    )
                    engineering = await asyncio.to_thread(
                        self._finish_engineering_run,
                        run_journal,
                        run_status,
                        files_changed=event.files_written,
                        input_tokens=event.input_tokens,
                        output_tokens=event.output_tokens,
                        cost_usd=event.cost_usd,
                    )
                    event.assistant_message = self._apply_completion_audit_notice(
                        event.assistant_message, engineering
                    )
                    self._replace_latest_assistant_message(event.assistant_message)
                    yield ChatStreamEvent(
                        type="engineering_complete",
                        engineering=engineering,
                    )
                yield event
            return

        total_input = 0
        total_output = 0
        total_cost = 0.0
        tool_calls: list[dict[str, Any]] = []
        files_written: list[str] = []
        final_content = ""
        read_cache: dict[str, ToolResult] = {}
        analysis_only = (
            not self._permission_allows_non_read_tools(run_journal.intent)
            or self.approval_mode == "readonly"
            or self._plan_mode_is_read_only()
        )
        read_file_keys: set[str] = set()

        iterations = 0
        while True:
            await asyncio.to_thread(self._maybe_compact_context)
            full_content = ""
            response_blocks: list[MessageContentBlock] = []
            provider_payload: list[dict[str, Any]] = []
            output_before = total_output
            usage_observed = False
            async for chunk in self.gateway.chat_with_main_model_stream(
                messages=self.session.messages,
                task_id=f"chat-{self.session.id}",
                max_tokens=4096,
                temperature=0.2,
                **self._native_kwargs(read_only=analysis_only),
            ):
                event = self._handle_stream_chunk(chunk)
                if event is not None:
                    if event.type == "delta":
                        full_content += chunk.content or ""
                    yield event
                if chunk.type == "usage":
                    if not usage_observed and chunk.input_tokens > 0 and not chunk.usage_estimated:
                        self._record_usage_observation(chunk.input_tokens)
                        usage_observed = True
                    total_input += chunk.input_tokens
                    total_output += chunk.output_tokens
                    total_cost += chunk.cost_usd
                elif chunk.type == "message_state":
                    response_blocks = chunk.content_blocks
                    provider_payload = chunk.provider_payload

            self._record_provider_trace(run_journal)
            final_content = self._strip_toolcall_artifacts(full_content)

            # 空响应守卫：无可解析文本且无工具调用时按失败处理，避免假完成。
            # 有 token 但无文本（任意轮）：可能是原生 tool_use/reasoning 未捕获；
            # 首轮零 token：Provider 无响应或模型 ID 不被识别。
            # 工具轮之后的零 token 空响应保持原有收尾行为。
            tokens_returned = total_output > output_before
            if not final_content.strip() and not self._has_tool_calls(
                full_content, response_blocks
            ) and (tokens_returned or iterations == 0):
                empty_reason = (
                    "模型未返回可解析文本"
                    if tokens_returned
                    else "模型无响应或返回空内容（0 token）"
                )
                empty_advice = (
                    "模型未返回可解析文本（可能输出了原生工具调用或推理内容），请重试或换一个模型。"
                    if tokens_returned
                    else "模型无响应或返回空内容（0 token）。请检查 Provider 连接与模型 ID 是否正确，或换一个模型重试。"
                )
                engineering = await asyncio.to_thread(
                    self._finish_engineering_run,
                    run_journal,
                    "failed",
                    input_tokens=total_input,
                    output_tokens=total_output,
                    cost_usd=total_cost,
                    residual_risks=[empty_reason],
                )
                yield ChatStreamEvent(
                    type="engineering_complete",
                    engineering=engineering,
                )
                yield ChatStreamEvent(
                    type="error",
                    error=empty_advice,
                )
                return

            self.session.add_message(
                "assistant",
                final_content,
                response_blocks,
                provider_payload,
            )

            if not self._has_tool_calls(full_content, response_blocks):
                break
            if iterations >= self.max_tool_iterations:
                # 达到最大工具轮数，追加提示并要求模型直接给出最终结果
                limit_specs = self._tool_specs(full_content, response_blocks)
                limit_calls = [
                    {
                        "tool": spec["tool"],
                        "params": spec.get("params", {}),
                        "success": False,
                        "error": "已达到最大工具调用次数",
                    }
                    for spec in limit_specs
                ]
                attach_tool_use_ids(limit_calls, limit_specs)
                tool_calls.extend(limit_calls)
                limit_prompt = "已达到最大工具调用次数，请基于已获得的信息直接完成用户请求，不要再调用工具。"
                self.session.add_message(
                    "user",
                    limit_prompt,
                    tool_result_blocks(limit_calls, limit_prompt),
                )
                full_content = ""
                final_blocks: list[MessageContentBlock] = []
                final_provider_payload: list[dict[str, Any]] = []
                usage_observed = False
                async for chunk in self.gateway.chat_with_main_model_stream(
                    messages=self.session.messages,
                    task_id=f"chat-{self.session.id}-finalize",
                    max_tokens=4096,
                    temperature=0.2,
                    **self._native_kwargs(read_only=analysis_only),
                ):
                    event = self._handle_stream_chunk(chunk)
                    if event is not None:
                        if event.type == "delta":
                            full_content += chunk.content or ""
                        yield event
                    if chunk.type == "usage":
                        if not usage_observed and chunk.input_tokens > 0 and not chunk.usage_estimated:
                            self._record_usage_observation(chunk.input_tokens)
                            usage_observed = True
                        total_input += chunk.input_tokens
                        total_output += chunk.output_tokens
                        total_cost += chunk.cost_usd
                    elif chunk.type == "message_state":
                        final_blocks = chunk.content_blocks
                        final_provider_payload = chunk.provider_payload
                self._record_provider_trace(run_journal)
                final_content = self._strip_toolcall_artifacts(full_content)
                self.session.add_message(
                    "assistant",
                    final_content,
                    final_blocks,
                    final_provider_payload,
                )
                break

            # 流式执行工具调用，期间可能产出 permission_request 事件
            tool_specs = self._tool_specs(full_content, response_blocks)
            calls: list[dict[str, Any]] = []
            tool_results_parts: list[str] = []

            for spec in tool_specs:
                tool_name = spec["tool"]
                params = spec.get("params", {})
                parse_error = spec.get("parse_error")

                if parse_error:
                    call = {
                        "tool": tool_name,
                        "params": {},
                        "success": False,
                        "error": f"参数解析失败：{parse_error}",
                    }
                    calls.append(call)
                    yield ChatStreamEvent(type="tool_complete", tool_call=call)
                    tool_results_parts.append(
                        f"\n[工具 {tool_name} 参数解析失败：{parse_error}]\n"
                    )
                    continue

                if (
                    tool_name == "run_command"
                    and command_correction_exhausted(run_journal.metrics)
                ):
                    result = command_correction_limit_result(
                        str(params.get("cwd", "."))
                    )
                    call = {
                        "tool": tool_name,
                        "params": params,
                        "success": False,
                        "output": result.output,
                        "error": result.error,
                        "cached": False,
                        "metadata": result.metadata,
                    }
                    calls.append(call)
                    yield ChatStreamEvent(type="tool_complete", tool_call=call)
                    tool_results_parts.append(self._format_tool_result(tool_name, result))
                    continue

                tool_spec = tool_registry.get(tool_name)
                category = tool_spec.category if tool_spec else "unknown"
                decision = self._active_permission_engine.decide(
                    tool_name,
                    params,
                    category=category,
                    approval_mode=self.approval_mode,
                    hard_read_only=analysis_only,
                )

                if decision.action == "deny":
                    denial_reason = decision.reason
                    if tool_name == "run_command":
                        denial_reason = (
                            f"{denial_reason}；{COMMAND_PERMISSION_GUIDANCE}"
                        )
                    call = {
                        "tool": tool_name,
                        "params": params,
                        "success": False,
                        "error": f"权限规则拒绝：{denial_reason}",
                        "permission": decision.summary(),
                        "metadata": {"error_code": "permission_denied"},
                    }
                    if tool_name == "run_command":
                        record_command_preflight_failure(
                            run_journal.metrics,
                            {"error_code": "permission_denied"},
                        )
                        await asyncio.to_thread(self.journal_store.save, run_journal)
                    calls.append(call)
                    yield ChatStreamEvent(type="tool_complete", tool_call=call)
                    tool_results_parts.append(
                        f"\n[工具 {tool_name} 被拒绝：{denial_reason}]\n"
                    )
                    continue

                cache_key = build_read_cache_key(tool_name, params, self.session.output_dir)
                if (
                    analysis_only
                    and tool_name == "read_file"
                    and cache_key not in read_cache
                    and cache_key not in read_file_keys
                    and len(read_file_keys) >= _ANALYSIS_READ_FILE_LIMIT
                ):
                    error = f"项目分析抽样已达到 {_ANALYSIS_READ_FILE_LIMIT} 个不同文件上限"
                    result = ToolResult(success=True, output=error)
                    call = {
                        "tool": tool_name,
                        "params": params,
                        "success": True,
                        "output": error,
                        "error": None,
                        "cached": False,
                        "skipped": True,
                    }
                    calls.append(call)
                    yield ChatStreamEvent(type="tool_complete", tool_call=call)
                    tool_results_parts.append(self._format_tool_result(tool_name, result))
                    changed = await asyncio.to_thread(
                        self._record_tool_evidence,
                        run_journal,
                        tool_name,
                        params,
                        result,
                        skipped=True,
                    )
                    if changed:
                        yield ChatStreamEvent(
                            type="engineering_update",
                            engineering=run_journal.event_payload(),
                        )
                    continue
                if analysis_only and tool_name == "read_file" and cache_key:
                    read_file_keys.add(cache_key)

                if decision.action == "ask":
                    request_id = self._register_permission_request()
                    yield ChatStreamEvent(
                        type="permission_request",
                        permission_request={
                            "request_id": request_id,
                            "tool": tool_name,
                            "params": params,
                            "message": self._build_permission_message(tool_name, params),
                            "decision": decision.summary(),
                        },
                    )
                    approved = await self._wait_for_permission(request_id)
                    if not approved:
                        call = {
                            "tool": tool_name,
                            "params": params,
                            "success": False,
                            "error": "用户拒绝执行",
                            "permission": decision.summary(),
                            "metadata": {"error_code": "permission_denied"},
                        }
                        if tool_name == "run_command":
                            record_command_preflight_failure(
                                run_journal.metrics,
                                {"error_code": "permission_denied"},
                            )
                            await asyncio.to_thread(
                                self.journal_store.save, run_journal
                            )
                        calls.append(call)
                        yield ChatStreamEvent(type="tool_complete", tool_call=call)
                        tool_results_parts.append(f"\n[工具 {tool_name} 被用户拒绝]\n")
                        continue

                cached = bool(cache_key and cache_key in read_cache)
                mutation_metadata = file_mutation_metadata(
                    tool_name, params, self.session.output_dir
                )
                yield ChatStreamEvent(
                    type="tool_start",
                    tool_call={"tool": tool_name, "params": params, "cached": cached},
                )
                if cached:
                    result = read_cache[cache_key]  # type: ignore[index]
                else:
                    result = await asyncio.to_thread(
                        execute_tool_call, tool_name, params, self.session.output_dir
                    )
                    if cache_key and result.success:
                        read_cache[cache_key] = result
                    if should_invalidate_read_cache(tool_name):
                        read_cache.clear()
                cached = cached or bool(result.metadata.get("cached"))
                call = {
                    "tool": tool_name,
                    "params": params,
                    "success": result.success,
                    "output": result.output,
                    "error": result.error,
                    "cached": cached,
                    "mutation_metadata": mutation_metadata,
                    "metadata": result.metadata,
                    "permission": decision.summary(),
                }
                if tool_name == "run_command" and not result.success:
                    record_command_preflight_failure(
                        run_journal.metrics, result.metadata
                    )
                calls.append(call)
                yield ChatStreamEvent(type="tool_complete", tool_call=call)
                tool_results_parts.append(self._format_tool_result(tool_name, result))
                changed = await asyncio.to_thread(
                    self._record_tool_evidence,
                    run_journal,
                    tool_name,
                    params,
                    result,
                    cached=cached,
                    metadata={
                        "permission": decision.summary(),
                        **mutation_metadata,
                    },
                )
                if changed:
                    yield ChatStreamEvent(
                        type="engineering_update",
                        engineering=run_journal.event_payload(),
                    )
                self._record_written_file(tool_name, params, result, files_written)

            if not calls:
                break

            attach_tool_use_ids(calls, tool_specs)
            tool_calls.extend(calls)
            self.session.add_message(
                "user",
                "".join(tool_results_parts) + "\n\n请继续完成用户请求。",
                tool_result_blocks(calls),
            )
            iterations += 1

        if analysis_only and len(final_content) > _ANALYSIS_FINAL_CHAR_LIMIT:
            self.session.add_message(
                "user",
                "上一版答复过长。请基于已经获得的证据，重新输出一份不超过 3000 个汉字的完整答复。"
                "保留用户要求、关键结论、证据、风险和下一步；不要调用任何工具，"
                "不要在标题、表格或列表中途结束。只输出最终答复。",
            )
            concise_content = ""
            concise_blocks: list[MessageContentBlock] = []
            concise_provider_payload: list[dict[str, Any]] = []
            usage_observed = False
            async for chunk in self.gateway.chat_with_main_model_stream(
                messages=self.session.messages,
                task_id=f"chat-{self.session.id}-concise",
                max_tokens=4096,
                temperature=0.2,
            ):
                event = self._handle_stream_chunk(chunk)
                if event is not None:
                    if event.type == "delta":
                        concise_content += chunk.content or ""
                    yield event
                if chunk.type == "usage":
                    if not usage_observed and chunk.input_tokens > 0 and not chunk.usage_estimated:
                        self._record_usage_observation(chunk.input_tokens)
                        usage_observed = True
                    total_input += chunk.input_tokens
                    total_output += chunk.output_tokens
                    total_cost += chunk.cost_usd
                elif chunk.type == "message_state":
                    concise_blocks = chunk.content_blocks
                    concise_provider_payload = chunk.provider_payload
            self._record_provider_trace(run_journal)
            concise_content = self._strip_toolcall_artifacts(concise_content).strip()
            if concise_content:
                final_content = concise_content
                self.session.add_message(
                    "assistant",
                    final_content,
                    concise_blocks,
                    concise_provider_payload,
                )

        # 不再自动抽取代码块为 generated_N 文件；仅当本轮未写任何文件时兜底保存回复为 response.md
        if (
            self.approval_mode == "auto"
            and not self._plan_mode_is_read_only()
            and not files_written
            and final_content.strip()
        ):
            files_written.append(
                await asyncio.to_thread(
                    write_text_file, "response.md", final_content, self.session.output_dir
                )
            )

        if self.session.plan_mode in ("pending", "active") and final_content.strip():
            council_result = await asyncio.to_thread(
                self._refine_plan, user_input, final_content, run_journal
            )
            final_content = council_result.content
            total_input += council_result.input_tokens
            total_output += council_result.output_tokens
            total_cost += council_result.cost_usd
            self._replace_latest_assistant_message(final_content)
            self.session.save_plan_artifact(
                final_content, council=council_result.summary()
            )

        engineering = await asyncio.to_thread(
            self._finish_engineering_run,
            run_journal,
            "completed",
            files_changed=files_written,
            input_tokens=total_input,
            output_tokens=total_output,
            cost_usd=total_cost,
        )
        final_content = self._apply_completion_audit_notice(final_content, engineering)
        self._replace_latest_assistant_message(final_content)
        yield ChatStreamEvent(
            type="engineering_complete",
            engineering=engineering,
        )

        yield ChatStreamEvent(
            type="done",
            assistant_message=final_content,
            tool_calls=tool_calls,
            files_written=files_written,
            input_tokens=total_input,
            output_tokens=total_output,
            cost_usd=total_cost,
        )

    async def _should_collaborate(
        self,
        user_input: str,
        intent: TaskIntent | None = None,
    ) -> bool:
        """是否需要多模型协作：先做关键字预筛，再交 LLM 判断"""
        resolved_intent = intent or self.intent_classifier.classify(
            user_input,
            self.approval_mode,
        )
        # 只读和未分类任务保持单 Agent，避免协作扩大权限或重复侦察。
        if not resolved_intent.policy.collaboration_allowed:
            return False
        # 关键字预筛：明确的项目/多步骤任务直接走协作
        if any(kw in user_input for kw in _COLLABORATION_KEYWORDS):
            return True

        messages = [
            ChatMessage(role="system", content=COLLABORATION_DECISION_PROMPT),
            ChatMessage(role="user", content=user_input),
        ]
        try:
            response = await asyncio.to_thread(
                self.gateway.chat_with_main_model,
                messages=messages,
                task_id=f"chat-{self.session.id}-decide",
                max_tokens=64,
                temperature=0.1,
            )
            content = response.content.strip()
            # 尝试直接解析 JSON
            if content.startswith("{"):
                data = json.loads(content)
                return bool(data.get("collaborate"))
            # 兜底：关键字匹配
            return "yes" in content.lower() or "true" in content.lower()
        except Exception:
            # 判断失败时保守走单模型路径
            return False

    async def _run_collaboration_stream(
        self,
        user_input: str,
        billing_before: dict[str, Any],
        run_journal: RunJournal,
    ) -> AsyncIterator[ChatStreamEvent]:
        """多模型协作流：Orchestrator -> Dispatcher -> Reviewer"""
        from src.core.dispatcher import Dispatcher
        from src.core.orchestrator import Orchestrator
        from src.core.reviewer import Reviewer
        from src.core.worker import Worker, load_workers_config

        # 构建记忆上下文
        memory_context = ""
        if self.memory_store and self.memory_store.config.enabled:
            builder = MemoryContextBuilder(self.memory_store)
            memory_context = builder.build_context(user_input)

        # 1. Orchestrator 规划
        project_rules = self._active_project_rules.prompt()
        orchestrator = Orchestrator(self.gateway, project_rules=project_rules)
        plan = await asyncio.to_thread(
            orchestrator.plan,
            user_request=user_input,
            memory_context=memory_context,
        )
        collaboration_roles = [
            {
                "role": "orchestrator",
                "task_id": "orchestrator",
                "planned_model": (
                    orchestrator.model if isinstance(orchestrator.model, str) else ""
                ),
                "actual_model": (
                    orchestrator.model if isinstance(orchestrator.model, str) else ""
                ),
                "status": "completed",
                **_response_usage(getattr(orchestrator, "last_response", None)),
            },
            *[
                {
                    "role": task.frontend_stage or task.type,
                    "task_id": task.id,
                    "planned_model": task.assigned_model,
                    "actual_model": "",
                    "status": "planned",
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cost_usd": 0.0,
                }
                for task in plan.tasks
            ],
        ]
        run_journal.metrics["collaboration"] = {
            "roles": collaboration_roles,
            "distinct_roles": len({item["role"] for item in collaboration_roles}),
            "distinct_models": len({
                item["planned_model"]
                for item in collaboration_roles
                if item["planned_model"]
            }),
        }
        yield ChatStreamEvent(
            type="plan",
            plan={
                "summary": plan.summary,
                "tasks": [
                    {
                        "id": t.id,
                        "type": t.type,
                        "title": t.title,
                        "assigned_model": t.assigned_model,
                        "execution_mode": t.execution_mode,
                        "owned_paths": t.owned_paths,
                        "parallel_safe": t.parallel_safe,
                        "max_retries": t.max_retries,
                        "acceptance": t.acceptance,
                        "frontend_stage": t.frontend_stage,
                    }
                    for t in plan.tasks
                ],
                "frontend_contract": (
                    plan.frontend_contract.model_dump()
                    if plan.frontend_contract is not None
                    else None
                ),
            },
        )

        # 1.5 协作前置批量确认：approve 模式下，dispatch 前一次性征求用户同意
        if self.approval_mode == "approve":
            request_id = self._register_permission_request()
            yield ChatStreamEvent(
                type="permission_request",
                permission_request={
                    "request_id": request_id,
                    "tool": "collaboration",
                    "params": {
                        "output_dir": self.session.output_dir,
                        "task_count": len(plan.tasks),
                        "tasks": [
                            {"id": t.id, "type": t.type, "title": t.title}
                            for t in plan.tasks
                        ],
                    },
                    "message": (
                        f"将执行 {len(plan.tasks)} 个子任务并自动写入文件到 "
                        f"{self.session.output_dir}，是否批准？"
                    ),
                },
            )
            approved = await self._wait_for_permission(request_id)
            if not approved:
                self.session.add_message("assistant", "协作已取消。")
                yield ChatStreamEvent(
                    type="done",
                    assistant_message="协作已取消。",
                    tool_calls=[],
                    files_written=[],
                    input_tokens=0,
                    output_tokens=0,
                    cost_usd=0.0,
                )
                return

        # 2. Dispatcher 并发执行（带进度回调）
        loop = asyncio.get_event_loop()
        queue: asyncio.Queue = asyncio.Queue()
        error_info: dict[str, str] | None = None
        dispatch_results: list[TaskResult] = []

        def _progress(event_type: str, payload: dict[str, Any]):
            asyncio.run_coroutine_threadsafe(queue.put((event_type, payload)), loop)

        def _dispatch():
            nonlocal error_info
            try:
                workers_config = load_workers_config()
                worker = Worker(
                    self.gateway,
                    workers_config,
                    project_rules=project_rules,
                    permission_engine=self._active_permission_engine,
                    approval_mode="auto",
                )
                dispatcher = Dispatcher(worker, max_workers=4)
                completed_results = dispatcher.dispatch(
                    plan,
                    output_dir=self.session.output_dir,
                    progress_callback=_progress,
                    memory_context=memory_context,
                )
                dispatch_results.extend(completed_results)
            except Exception as exc:  # noqa: BLE001
                error_info = {"error": str(exc)}
                _progress("__error__", error_info)
            finally:
                _progress("__done__", {})

        thread = threading.Thread(target=_dispatch, daemon=True)
        thread.start()

        while True:
            event_type, payload = await queue.get()
            if event_type == "__done__":
                break
            if event_type == "__error__":
                yield ChatStreamEvent(type="error", error=payload.get("error", "未知错误"))
                return
            yield ChatStreamEvent(type=event_type, task=payload)

        results = list(dispatch_results)
        evidence_changed = False
        for result in results:
            role_entry = next(
                (
                    item
                    for item in collaboration_roles
                    if item["task_id"] == result.task.id
                ),
                None,
            )
            if role_entry is not None:
                role_entry["status"] = "completed" if result.success else "failed"
                role_entry["actual_model"] = (
                    result.response.model if result.response is not None else ""
                )
                role_entry.update(_response_usage(result.response))
            excerpt = (result.content if result.success else result.error).strip()
            _, added = run_journal.add_evidence(
                Evidence(
                    source=f"worker:{result.task.id}",
                    claim=(
                        f"Worker {result.task.id} 执行成功"
                        if result.success
                        else f"Worker {result.task.id} 执行失败"
                    ),
                    excerpt=excerpt[:800],
                    kind="runtime",
                    success=result.success,
                    metadata={
                        "task_id": result.task.id,
                        "task_type": result.task.type,
                        "files_written": result.files_written,
                        "attempts": result.attempts,
                        "retry_errors": result.retry_errors,
                        "acceptance_evidence": result.acceptance_evidence,
                    },
                )
            )
            evidence_changed = evidence_changed or added
            for call in result.tool_calls:
                tool_name = str(call.get("tool", "unknown"))
                params = call.get("params", {}) or {}
                tool_result = ToolResult(
                    success=bool(call.get("success", False)),
                    output=str(call.get("output", "")),
                    error=str(call.get("error", "")),
                    metadata=call.get("metadata") or {},
                )
                changed = self.evidence_recorder.record(
                    run_journal,
                    tool_name,
                    params,
                    tool_result,
                    cached=bool(call.get("cached", False)),
                    source=f"worker:{result.task.id}:tool:{tool_name}",
                    metadata={
                        "worker_task_id": result.task.id,
                        "worker_type": result.task.type,
                        **(call.get("metadata") or {}),
                        "permission": call.get("permission") or {},
                        **(call.get("mutation_metadata") or {}),
                    },
                )
                verification_changed = self.verification_tracker.record(
                    run_journal,
                    tool_name,
                    params,
                    tool_result,
                    cached=bool(call.get("cached", False)),
                )
                evidence_changed = evidence_changed or changed or verification_changed
        run_journal.metrics["collaboration"]["distinct_models"] = len({
            item["actual_model"] or item["planned_model"]
            for item in collaboration_roles
            if item["actual_model"] or item["planned_model"]
        })
        self.completion_auditor.audit(run_journal, "completed")
        await asyncio.to_thread(self.journal_store.save, run_journal)
        if evidence_changed or run_journal.audit is not None:
            yield ChatStreamEvent(
                type="engineering_update",
                engineering=run_journal.event_payload(),
            )

        # 3. Reviewer 整合
        reviewer = Reviewer(self.gateway, project_rules=project_rules)
        review = await asyncio.to_thread(
            reviewer.review,
            user_request=user_input,
            plan=plan,
            results=results,
            engineering_context={
                "evidence": [item.model_dump() for item in run_journal.evidence],
                "verification": [
                    item.model_dump() for item in run_journal.verification
                ],
                "requirements": [
                    item.model_dump() for item in run_journal.requirements
                ],
                "audit": run_journal.audit.model_dump() if run_journal.audit else None,
            },
        )
        reviewer_input_mode = (
            reviewer.input_mode
            if isinstance(getattr(reviewer, "input_mode", None), str)
            else "restricted"
        )
        collaboration_roles.append({
            "role": "reviewer",
            "task_id": "reviewer",
            "planned_model": (
                reviewer.model if isinstance(reviewer.model, str) else ""
            ),
            "actual_model": (
                reviewer.model if isinstance(reviewer.model, str) else ""
            ),
            "status": "completed" if review.passed else "failed",
            "input_mode": reviewer_input_mode,
            **_response_usage(getattr(reviewer, "last_response", None)),
        })
        run_journal.metrics["collaboration"]["reviewer_input_mode"] = (
            reviewer_input_mode
        )
        run_journal.metrics["collaboration"]["distinct_roles"] = len({
            item["role"] for item in collaboration_roles
        })
        run_journal.metrics["collaboration"]["distinct_models"] = len({
            item["actual_model"] or item["planned_model"]
            for item in collaboration_roles
            if item["actual_model"] or item["planned_model"]
        })
        await asyncio.to_thread(self.journal_store.save, run_journal)
        yield ChatStreamEvent(
            type="review_complete",
            review={
                "passed": review.passed,
                "issues": review.issues,
                "final_output": review.final_output,
                "audit": run_journal.audit.model_dump() if run_journal.audit else None,
            },
        )

        # 4. 追加最终答案到 Session
        self.session.add_message("assistant", review.final_output)

        # 5. 计算本次协作成本
        billing_after = self.gateway.billing.summary()
        total_input = billing_after["total_input_tokens"] - billing_before["total_input_tokens"]
        total_output = billing_after["total_output_tokens"] - billing_before["total_output_tokens"]
        total_cost = billing_after["total_cost_usd"] - billing_before["total_cost_usd"]

        all_files: list[str] = []
        for r in results:
            all_files.extend(r.files_written)

        # 6. 仅当协作未产出文件时，兜底保存 Reviewer 最终输出为 response.md
        if self.approval_mode == "auto" and not all_files and review.final_output.strip():
            all_files.append(
                await asyncio.to_thread(
                    write_text_file, "response.md", review.final_output, self.session.output_dir
                )
            )

        yield ChatStreamEvent(
            type="done",
            assistant_message=review.final_output,
            tool_calls=[],
            files_written=all_files,
            input_tokens=total_input,
            output_tokens=total_output,
            cost_usd=total_cost,
        )
