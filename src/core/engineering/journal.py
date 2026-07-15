"""RunJournal YAML 持久化。"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

from src.core.engineering.models import ProjectReconnaissance, RunJournal, TaskIntent
from src.models.schemas import ApprovalMode


_SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9_-]+$")


class RunJournalStore:
    """会话内运行记录存储，使用原子替换避免半写 YAML。"""

    def __init__(self, runs_dir: str | Path):
        self.runs_dir = Path(runs_dir)

    @classmethod
    def from_output_dir(cls, output_dir: str | Path) -> "RunJournalStore":
        return cls(Path(output_dir).parent / "runs")

    def create(
        self,
        session_id: str,
        objective: str,
        approval_mode: ApprovalMode,
        intent: TaskIntent | None = None,
    ) -> RunJournal:
        run_id = (
            datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
            + "-"
            + uuid.uuid4().hex[:6]
        )
        resolved_intent = intent or TaskIntent()
        if resolved_intent.kind == "unclassified":
            decision = (
                f"Phase 7.1 未能稳定分类；按会话权限模式 {approval_mode} "
                "和保守只读策略记录边界。"
            )
        else:
            access = (
                "项目写入已授权"
                if resolved_intent.write_authorized
                else "只读或写入尚未授权"
            )
            decision = (
                f"任务分类为 {resolved_intent.kind}（{resolved_intent.classification_source}，"
                f"置信度 {resolved_intent.confidence:.2f}）；{access}。"
            )
        journal = RunJournal(
            run_id=run_id,
            session_id=session_id,
            objective=objective,
            intent=resolved_intent,
            reconnaissance=ProjectReconnaissance(
                root=resolved_intent.scope[0] if resolved_intent.scope else ""
            ),
            decisions=[decision],
        )
        self.save(journal)
        return journal

    def _path(self, run_id: str) -> Path:
        if not _SAFE_RUN_ID.fullmatch(run_id):
            raise ValueError(f"非法 run_id：{run_id}")
        return self.runs_dir / f"{run_id}.yaml"

    def save(self, journal: RunJournal) -> Path:
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        path = self._path(journal.run_id)
        temp_path = path.with_suffix(".yaml.tmp")
        with temp_path.open("w", encoding="utf-8", newline="\n") as stream:
            yaml.safe_dump(
                journal.model_dump(),
                stream,
                allow_unicode=True,
                sort_keys=False,
                default_flow_style=False,
            )
        temp_path.replace(path)
        return path

    def load(self, run_id: str) -> RunJournal:
        path = self._path(run_id)
        if not path.exists():
            raise FileNotFoundError(f"运行记录不存在：{run_id}")
        with path.open("r", encoding="utf-8") as stream:
            data = yaml.safe_load(stream) or {}
        return RunJournal(**data)

    def list(self) -> list[RunJournal]:
        if not self.runs_dir.exists():
            return []
        journals = []
        for path in self.runs_dir.glob("*.yaml"):
            with path.open("r", encoding="utf-8") as stream:
                journals.append(RunJournal(**(yaml.safe_load(stream) or {})))
        return sorted(journals, key=lambda item: item.started_at, reverse=True)

    def latest(self) -> RunJournal | None:
        journals = self.list()
        return journals[0] if journals else None
