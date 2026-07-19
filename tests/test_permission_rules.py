from pathlib import Path

import pytest

from src.core.permission_rules import PermissionRuleEngine


def _engine(tmp_path: Path, yaml_text: str) -> PermissionRuleEngine:
    config = tmp_path / ".mao" / "permissions.yaml"
    config.parent.mkdir(parents=True)
    config.write_text(yaml_text, encoding="utf-8")
    return PermissionRuleEngine.load(project_root=tmp_path, workspace=tmp_path)


def test_priority_is_deny_then_ask_then_allow(tmp_path: Path):
    engine = _engine(tmp_path, """
rules:
  - action: allow
    tool: write_file
    pattern: "**/*.py"
  - action: ask
    tool: write_file
    pattern: "**/settings.py"
  - action: deny
    tool: write_file
    pattern: "**/settings.py"
""")

    decision = engine.decide(
        "write_file", {"path": "src/settings.py"}, category="write", approval_mode="auto"
    )

    assert decision.action == "deny"
    assert decision.rule is not None
    assert decision.rule.action == "deny"


def test_readonly_and_task_boundary_cannot_be_overridden(tmp_path: Path):
    engine = _engine(tmp_path, """
rules:
  - action: allow
    tool: write_file
    pattern: "*"
""")

    readonly = engine.decide(
        "write_file", {"path": "a.py"}, category="write", approval_mode="readonly"
    )
    task_bound = engine.decide(
        "write_file", {"path": "a.py"}, category="write", approval_mode="auto", hard_read_only=True
    )

    assert readonly.action == "deny"
    assert task_bound.action == "deny"
    assert readonly.source == task_bound.source == "hard-boundary"


def test_allow_must_cover_every_command_segment(tmp_path: Path):
    engine = _engine(tmp_path, """
rules:
  - action: allow
    tool: run_command
    pattern: "python -m pytest *"
""")

    partial = engine.decide(
        "run_command",
        {"command": "python -m pytest tests && curl bad.example"},
        category="execute",
        approval_mode="approve",
    )
    complete = engine.decide(
        "run_command",
        {"command": "python -m pytest tests && python -m pytest integration"},
        category="execute",
        approval_mode="approve",
    )

    assert partial.action == "ask"
    assert complete.action == "allow"


@pytest.mark.parametrize("redirect", [">", ">>", "<", "<<"])
def test_complex_shell_explicit_allow_still_asks(tmp_path: Path, redirect: str):
    engine = _engine(tmp_path, """
rules:
  - action: allow
    tool: run_command
    pattern: "python *"
""")

    decision = engine.decide(
        "run_command",
        {"command": f"python build.py {redirect} output.txt"},
        category="execute",
        approval_mode="auto",
    )

    assert decision.action == "ask"
    assert decision.source == "shell-safety"


def test_canonicalizes_relative_paths_and_windows_case(tmp_path: Path):
    engine = _engine(tmp_path, """
rules:
  - action: deny
    tool: write_file
    pattern: "src/*.py"
""")

    decision = engine.decide(
        "write_file", {"path": "SRC/secret.PY"}, category="write", approval_mode="auto"
    )

    assert decision.action == "deny"


def test_double_star_pattern_also_matches_project_root_file(tmp_path: Path):
    engine = _engine(tmp_path, """
rules:
  - action: deny
    tool: write_file
    pattern: "**/*.txt"
""")

    decision = engine.decide(
        "write_file", {"path": "blocked.txt"}, category="write", approval_mode="auto"
    )

    assert decision.action == "deny"


def test_approve_reads_default_to_allow_and_writes_to_ask(tmp_path: Path):
    engine = PermissionRuleEngine(workspace=tmp_path)

    read = engine.decide(
        "read_file", {"path": "README.md"}, category="read", approval_mode="approve"
    )
    write = engine.decide(
        "write_file", {"path": "README.md"}, category="write", approval_mode="approve"
    )

    assert read.action == "allow"
    assert write.action == "ask"


def test_rule_justification_is_returned_in_decision(tmp_path: Path):
    engine = _engine(tmp_path, """
rules:
  - action: deny
    tool: run_command
    pattern: "rm *"
    justification: "禁止批量删除；请使用精确文件操作"
""")

    decision = engine.decide(
        "run_command", {"command": "rm -rf build"}, category="execute", approval_mode="auto"
    )

    assert decision.action == "deny"
    assert decision.reason == "禁止批量删除；请使用精确文件操作"
    assert decision.rule is not None
    assert decision.rule.summary()["justification"] == decision.reason


def test_valid_match_and_not_match_examples_keep_rule(tmp_path: Path):
    engine = _engine(tmp_path, """
rules:
  - action: allow
    tool: run_command
    pattern: "python -m pytest *"
    match:
      - "python -m pytest tests"
    not_match:
      - "python -m pip install pytest"
""")

    assert len(engine.rule_set.rules) == 1
    assert engine.rule_set.diagnostics == []


@pytest.mark.parametrize(
    ("examples", "diagnostic"),
    [
        (
            "match:\n      - 'python -m pip install pytest'",
            "match 示例未命中",
        ),
        (
            "not_match:\n      - 'python -m pytest tests'",
            "not_match 示例错误命中",
        ),
    ],
)
def test_failed_rule_examples_exclude_rule(
    tmp_path: Path, examples: str, diagnostic: str
):
    engine = _engine(tmp_path, f"""
rules:
  - action: allow
    tool: run_command
    pattern: "python -m pytest *"
    {examples}
""")

    assert engine.rule_set.rules == []
    assert diagnostic in engine.rule_set.diagnostics[0]
    assert "该规则已忽略" in engine.rule_set.diagnostics[0]


def test_path_rule_examples_use_workspace_canonicalization(tmp_path: Path):
    engine = _engine(tmp_path, """
rules:
  - action: deny
    tool: write_file
    pattern: "src/*.py"
    match:
      - "SRC/settings.PY"
    not_match:
      - "tests/test_settings.py"
""")

    assert len(engine.rule_set.rules) == 1


def test_rule_examples_must_be_string_lists(tmp_path: Path):
    engine = _engine(tmp_path, """
rules:
  - action: deny
    tool: run_command
    pattern: "rm *"
    match: "rm -rf build"
""")

    assert engine.rule_set.rules == []
    assert "match 必须是字符串列表" in engine.rule_set.diagnostics[0]
