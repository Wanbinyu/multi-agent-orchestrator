"""Phase 7.1 保守任务分类与执行策略。"""
from __future__ import annotations

import re
from dataclasses import dataclass

from src.core.engineering.models import (
    RiskLevel,
    TaskExecutionPolicy,
    TaskIntent,
    TaskKind,
    VerificationDepth,
)
from src.models.schemas import ApprovalMode


@dataclass(frozen=True)
class _PolicyPreset:
    risk_level: RiskLevel
    allow_project_writes: bool
    requires_plan: bool
    verification_depth: VerificationDepth
    collaboration_allowed: bool
    deliverables: tuple[str, ...]


_POLICIES: dict[TaskKind, _PolicyPreset] = {
    "unclassified": _PolicyPreset(
        "medium", False, False, "targeted", False, ("保守只读答复",)
    ),
    "answer": _PolicyPreset("low", False, False, "none", False, ("直接答复",)),
    "explain": _PolicyPreset(
        "low", False, False, "targeted", False, ("解释说明",)
    ),
    "diagnose": _PolicyPreset(
        "medium", False, False, "targeted", False, ("根因", "证据", "未验证区域")
    ),
    "change": _PolicyPreset(
        "medium", True, False, "standard", True, ("代码修改", "验证结果")
    ),
    "build": _PolicyPreset(
        "high", True, True, "deep", True, ("功能实现", "测试", "使用说明")
    ),
    "review": _PolicyPreset(
        "medium", False, False, "standard", False, ("问题清单", "证据", "剩余风险")
    ),
    "plan": _PolicyPreset(
        "low", False, True, "targeted", False, ("实施方案", "风险", "验收标准")
    ),
    "monitor": _PolicyPreset(
        "external", False, False, "continuous", False, ("状态更新", "异常通知")
    ),
}

_CONTINUATION_PATTERNS = (
    r"^(继续|接着|继续执行|接着执行|执行下一步|开始执行|可以执行|可以，?执行|下一步)$",
    r"^(继续|接着)(做|处理|完成|修复|实现)?(下一步|剩余部分)?$",
)

_MONITOR_PATTERNS = (
    r"监控", r"持续检查", r"继续观察", r"盯着", r"定时检查", r"等待.*完成", r"有变化.*通知",
)
_PLAN_ONLY_PATTERNS = (
    r"只做方案", r"仅做方案", r"先做方案", r"只给方案", r"先做计划", r"制定.*计划",
    r"给出.*方案", r"重构方案", r"实施方案", r"迁移方案", r"规划一下",
)
_NO_WRITE_PATTERNS = (
    r"只分析", r"仅分析", r"只读", r"不要修改", r"不修改文件", r"先不要改", r"暂不实现",
)
_BUILD_PATTERNS = (
    r"开发(一个|一套|功能|系统|应用|网站|页面|接口)", r"实现(一个|一套|功能|系统|应用|网站|页面|接口)",
    r"^(开发|实现).*(功能|系统|应用|网站|页面|接口|模块)",
    r"新增(功能|页面|接口|模块|能力)", r"添加(功能|页面|接口|模块|能力)", r"创建(项目|系统|应用|网站|页面|接口|模块)",
    r"搭建", r"从零", r"做一个", r"做一套", r"写一个", r"写个", r"^写(入)?文件(?:$|[\s：:，,])", r"重做",
)
_CHANGE_PATTERNS = (
    r"修复", r"修改", r"改代码", r"调整", r"优化", r"重构", r"更新", r"升级", r"替换", r"删除", r"完善", r"补齐",
)
_DIAGNOSE_PATTERNS = (
    r"诊断", r"排查", r"定位.*(问题|故障|错误)", r"为什么.*(失败|报错|异常|重复|不工作)",
    r"原因.*(是什么|导致)", r"故障", r"报错", r"异常", r"根因",
)
_REVIEW_PATTERNS = (
    r"审查", r"审阅", r"代码\s*review", r"安全审计", r"检查.*(项目|代码|实现|差异|结构)",
    r"评估.*(项目|代码|架构|实现)", r"分析.*(项目|代码|结构|架构)",
)
_EXPLAIN_PATTERNS = (
    r"解释", r"说明", r"介绍", r"讲解", r"梳理", r"原理", r"怎么工作", r"如何工作", r"看懂",
)
_ANSWER_PATTERNS = (
    r"是什么", r"是多少", r"是否", r"能不能", r"可以吗", r"怎么", r"如何", r"告诉我", r"现在.*吗", r"有哪些", r"有没有",
)
_EXPLICIT_WRITE_PATTERNS = (
    r"^(修复|修改|调整|优化|重构|更新|升级|替换|删除|完善|补齐)",
    r"^(开发|实现|新增|添加|创建|搭建|从零|做一个|做一套|写一个|写个|写文件|写入文件|重做)",
    r"^(请|请帮我|帮我)(修复|修改|调整|优化|重构|更新|升级|替换|删除|完善|补齐|开发|实现|新增|添加|创建|搭建|写)",
    r"(开始|执行|直接|现在进行|现在开始)(修复|修改|调整|优化|重构|更新|升级|替换|删除|开发|实现|创建|搭建)",
    r"并(修复|修改|调整|优化|重构|更新|替换|删除|实现)",
    r"可以改代码", r"把.+(改成|修改为|替换为|删除|做成|做一个|实现为|开发成)", r"综合.*做",
)

_WINDOWS_PATH = re.compile(r"(?<!\w)([A-Za-z]:[\\/][^\s，。；;!?\"'`]+)")
_BACKTICK_PATH = re.compile(r"`([^`]+[\\/][^`]+)`")


def _matches(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def _extract_scope(text: str) -> list[str]:
    matches = [*(_WINDOWS_PATH.findall(text)), *(_BACKTICK_PATH.findall(text))]
    return list(dict.fromkeys(value.rstrip(".,，。") for value in matches))


class TaskIntentClassifier:
    """零模型调用分类器；不确定时保持只读。"""

    def classify(
        self,
        user_input: str,
        approval_mode: ApprovalMode,
        previous_intent: TaskIntent | None = None,
    ) -> TaskIntent:
        text = " ".join(user_input.strip().split())
        normalized = text.lower()

        if previous_intent and self._is_continuation(normalized):
            return self._build_intent(
                previous_intent.kind,
                approval_mode,
                scope=previous_intent.scope,
                source="inherited",
                confidence=min(max(previous_intent.confidence, 0.7), 0.9),
                note=f"短续接请求继承上一轮 {previous_intent.kind} 意图",
            )

        kind, confidence, note = self._classify_kind(normalized)
        source = "fallback" if kind == "unclassified" else "rules"
        return self._build_intent(
            kind,
            approval_mode,
            scope=_extract_scope(text),
            source=source,
            confidence=confidence,
            note=note,
        )

    @staticmethod
    def _is_continuation(text: str) -> bool:
        return _matches(text, _CONTINUATION_PATTERNS)

    @staticmethod
    def _classify_kind(text: str) -> tuple[TaskKind, float, str]:
        if _matches(text, _MONITOR_PATTERNS):
            return "monitor", 0.96, "命中持续观察或通知请求"

        plan_only = _matches(text, _PLAN_ONLY_PATTERNS)
        no_write = _matches(text, _NO_WRITE_PATTERNS)
        explicit_write = _matches(text, _EXPLICIT_WRITE_PATTERNS)
        question_like = _matches(text, _ANSWER_PATTERNS) or text.endswith(("?", "？"))
        if plan_only:
            return "plan", 0.97, "命中仅制定方案、不实施的明确边界"
        if no_write and _matches(text, _DIAGNOSE_PATTERNS):
            return "diagnose", 0.96, "命中只读故障诊断请求"
        if no_write and _matches(text, _REVIEW_PATTERNS):
            return "review", 0.96, "命中只读项目审查请求"

        if question_like and not explicit_write:
            if _matches(text, _DIAGNOSE_PATTERNS):
                return "diagnose", 0.91, "命中只读故障问询"
            if _matches(text, _REVIEW_PATTERNS):
                return "review", 0.91, "命中只读检查或评估问询"
            if _matches(text, _EXPLAIN_PATTERNS):
                return "explain", 0.88, "命中解释问询"
            return "answer", 0.84, "命中直接问答且没有明确写入授权"

        # 明确写入动词优先于“检查并修复”中的检查词。
        if explicit_write and _matches(text, _BUILD_PATTERNS):
            return "build", 0.94, "命中新功能或新项目实现请求"
        if explicit_write and _matches(text, _CHANGE_PATTERNS):
            return "change", 0.94, "命中现有内容修改或修复请求"
        if _matches(text, _DIAGNOSE_PATTERNS):
            return "diagnose", 0.91, "命中故障、错误或根因分析请求"
        if _matches(text, _REVIEW_PATTERNS):
            return "review", 0.91, "命中项目、代码或差异审查请求"
        if _matches(text, _EXPLAIN_PATTERNS):
            return "explain", 0.88, "命中解释或原理说明请求"
        if question_like:
            return "answer", 0.82, "命中直接问答请求"
        return "unclassified", 0.3, "未命中稳定规则，采用保守只读策略"

    @staticmethod
    def _build_intent(
        kind: TaskKind,
        approval_mode: ApprovalMode,
        *,
        scope: list[str],
        source: str,
        confidence: float,
        note: str,
    ) -> TaskIntent:
        preset = _POLICIES[kind]
        policy = TaskExecutionPolicy(
            allow_project_writes=preset.allow_project_writes,
            requires_plan=preset.requires_plan,
            verification_depth=preset.verification_depth,
            collaboration_allowed=preset.collaboration_allowed,
        )
        return TaskIntent(
            kind=kind,
            scope=scope,
            risk_level=preset.risk_level,
            write_authorized=(
                preset.allow_project_writes and approval_mode == "auto"
            ),
            deliverables=list(preset.deliverables),
            policy=policy,
            classification_source=source,
            confidence=confidence,
            classification_note=note,
        )
