"""CLI `/runs` 本地工程记录查看命令测试"""
from types import SimpleNamespace

from src.cli.chat_command import _cmd_runs
from src.core.engineering.journal import RunJournalStore
from src.core.engineering.models import (
    CompletionAudit,
    Evidence,
    VerificationGate,
    WorkPlan,
    WorkPlanStep,
)


def _make_session_with_runs(tmp_path):
    """构造带运行记录的伪会话（_cmd_runs 只读取 output_dir）。"""
    output_dir = tmp_path / "session-x" / "output"
    output_dir.mkdir(parents=True)
    store = RunJournalStore.from_output_dir(output_dir)
    journal = store.create(
        session_id="session-x",
        objective="检查项目并给出风险",
        approval_mode="approve",
    )
    journal.plan = WorkPlan(
        objective="检查项目并给出风险",
        steps=[
            WorkPlanStep(title="读取结构", status="completed"),
            WorkPlanStep(title="抽样核心代码", status="in_progress"),
        ],
        acceptance_criteria=["给出风险清单"],
    )
    journal.add_evidence(
        Evidence(source="project_tree", claim="项目包含 src 与 tests", kind="structure", path=".")
    )
    journal.add_verification(
        VerificationGate(
            requirement="测试通过",
            command_or_check="pytest -q",
            passed=True,
            check_type="targeted",
        )
    )
    journal.audit = CompletionAudit(status="passed", can_complete=True, summary="验证闭环")
    journal.files_changed = ["src/app.py"]
    journal.residual_risks = ["未做真实 smoke"]
    journal.metrics = {"tool_calls": 3}
    store.save(journal)
    return SimpleNamespace(output_dir=str(output_dir)), journal.run_id


def test_cmd_runs_lists_recent_journals(tmp_path, capsys):
    session, run_id = _make_session_with_runs(tmp_path)
    _cmd_runs(session, "")
    out = capsys.readouterr().out
    assert run_id in out
    assert "进行中" in out
    assert "本地读取" in out


def test_cmd_runs_prints_full_detail(tmp_path, capsys):
    session, run_id = _make_session_with_runs(tmp_path)
    _cmd_runs(session, run_id)
    out = capsys.readouterr().out
    assert "检查项目并给出风险" in out
    assert "工作计划" in out and "读取结构" in out
    assert "证据" in out and "项目包含 src 与 tests" in out
    assert "验证门" in out and "pytest -q" in out
    assert "完成审计" in out and "验证闭环" in out
    assert "src/app.py" in out
    assert "未做真实 smoke" in out
    assert "tool_calls = 3" in out


def test_cmd_runs_reports_missing_run(tmp_path, capsys):
    session = SimpleNamespace(output_dir=str(tmp_path / "out"))
    _cmd_runs(session, "missing-run")
    out = capsys.readouterr().out
    assert "不存在" in out or "非法" in out


def test_cmd_runs_empty_session(tmp_path, capsys):
    session = SimpleNamespace(output_dir=str(tmp_path / "out"))
    _cmd_runs(session, "")
    assert "暂无工程运行记录" in capsys.readouterr().out
