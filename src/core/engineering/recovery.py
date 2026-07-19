"""Deterministic interrupted-session detection and explicit recovery decisions."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from src.core.engineering.journal import RunJournalStore
from src.core.engineering.models import RunJournal, utc_now
from src.core.session import Session, SessionRecoveryDecision


class RecoveryState(BaseModel):
    required: bool = False
    run_id: str = ""
    run_status: str = ""
    objective: str = ""
    reason: str = ""
    unfinished_steps: list[dict[str, str]] = Field(default_factory=list)
    completed_steps: list[dict[str, str]] = Field(default_factory=list)
    files_changed: list[str] = Field(default_factory=list)
    prior_action: Literal["continue", "abandon"] | None = None

    @property
    def unfinished_step_count(self) -> int:
        return len(self.unfinished_steps)

    def public_payload(self) -> dict:
        return {
            **self.model_dump(),
            "unfinished_step_count": self.unfinished_step_count,
        }


class RecoveryConfirmationRequired(RuntimeError):
    def __init__(self, state: RecoveryState):
        super().__init__(
            "检测到未确认的中断任务；请先选择继续或放弃，系统不会自动重放。"
        )
        self.state = state


class SessionRecoveryManager:
    """Inspect and acknowledge only the latest local engineering run."""

    def __init__(self, session: Session, run_store: RunJournalStore | None = None):
        self.session = session
        self.run_store = run_store or RunJournalStore.from_output_dir(session.output_dir)

    def inspect(self) -> RecoveryState:
        journal = self.run_store.latest()
        if journal is None:
            return RecoveryState()
        unfinished, completed = self._partition_steps(journal)
        interrupted = journal.status in {"running", "blocked"}
        if not interrupted and not unfinished:
            return RecoveryState()
        prior = next(
            (
                item
                for item in reversed(self.session.recovery_decisions)
                if item.run_id == journal.run_id
            ),
            None,
        )
        if prior is not None:
            return RecoveryState(
                run_id=journal.run_id,
                run_status=journal.status,
                objective=journal.objective,
                reason=self._reason(journal, unfinished),
                unfinished_steps=unfinished,
                completed_steps=completed,
                files_changed=list(journal.files_changed),
                prior_action=prior.action,
            )
        return RecoveryState(
            required=True,
            run_id=journal.run_id,
            run_status=journal.status,
            objective=journal.objective,
            reason=self._reason(journal, unfinished),
            unfinished_steps=unfinished,
            completed_steps=completed,
            files_changed=list(journal.files_changed),
        )

    def require_ready(self) -> None:
        state = self.inspect()
        if state.required:
            raise RecoveryConfirmationRequired(state)

    def decide(self, action: Literal["continue", "abandon"]) -> RecoveryState:
        state = self.inspect()
        if not state.required:
            raise ValueError("当前会话没有等待确认的中断任务")
        journal = self.run_store.load(state.run_id)
        decision = SessionRecoveryDecision(
            run_id=journal.run_id,
            action=action,
            status_before=journal.status,
            unfinished_step_ids=[item["id"] for item in state.unfinished_steps],
            unfinished_step_titles=[item["title"] for item in state.unfinished_steps],
            completed_step_ids=[item["id"] for item in state.completed_steps],
            completed_step_titles=[item["title"] for item in state.completed_steps],
            files_changed=list(journal.files_changed),
        )
        if action == "continue":
            message = (
                "[recovery] 用户确认继续中断任务；后续只处理未完成步骤，"
                "不得自动重放已完成步骤或重复写入既有文件。"
            )
        else:
            message = (
                "[recovery] 用户放弃中断任务；保留既有证据和文件，"
                "不自动回滚、不重放任何步骤。"
            )
            self._abandon_unfinished_steps(journal)
        if message not in journal.decisions:
            journal.decisions.append(message)
        if journal.status in {"running", "completed"}:
            residual_risk = (
                "运行被中断；恢复决定已记录，旧 run 不会自动重放。"
                if journal.status == "running"
                else "运行记录标记为完成，但计划仍有未完成步骤；已按受阻状态收口。"
            )
            journal.finish(
                "blocked",
                residual_risks=[residual_risk],
            )
        else:
            journal.updated_at = utc_now()
        self.run_store.save(journal)
        self.session.record_recovery_decision(decision)
        return self.inspect()

    def claim_checkpoint(self, new_run_id: str) -> SessionRecoveryDecision | None:
        for decision in reversed(self.session.recovery_decisions):
            if decision.action != "continue" or decision.consumed_by_run_id is not None:
                continue
            decision.consumed_by_run_id = new_run_id
            self.session.updated_at = datetime.now(timezone.utc).isoformat()
            return decision
        return None

    @staticmethod
    def _partition_steps(journal: RunJournal) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
        unfinished: list[dict[str, str]] = []
        completed: list[dict[str, str]] = []
        if journal.plan is None:
            return unfinished, completed
        for step in journal.plan.steps:
            item = {"id": step.id, "title": step.title, "status": step.status}
            if step.status == "completed":
                completed.append(item)
            else:
                unfinished.append(item)
        return unfinished, completed

    @staticmethod
    def _reason(journal: RunJournal, unfinished: list[dict[str, str]]) -> str:
        if journal.status == "running":
            return "上次运行在进程结束时仍处于进行中。"
        if journal.audit and journal.audit.summary:
            return journal.audit.summary
        if journal.residual_risks:
            return journal.residual_risks[0]
        if unfinished:
            return f"工作计划仍有 {len(unfinished)} 个未完成步骤。"
        return "上次运行处于受阻状态。"

    @staticmethod
    def _abandon_unfinished_steps(journal: RunJournal) -> None:
        if journal.plan is None:
            return
        for step in journal.plan.steps:
            if step.status in {"pending", "in_progress"}:
                step.status = "blocked"
                step.note = "用户在会话恢复确认中放弃该步骤。"
        journal.plan._refresh_status()
        journal.plan.updated_at = utc_now()
