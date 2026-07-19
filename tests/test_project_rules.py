from pathlib import Path

from src.core.project_rules import ProjectRuleResolver


def test_loads_hierarchical_rules_from_root_to_target(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    (tmp_path / "AGENTS.md").write_text("root rule", encoding="utf-8")
    nested = tmp_path / "src" / "feature"
    nested.mkdir(parents=True)
    (tmp_path / "src" / "CLAUDE.md").write_text("src rule", encoding="utf-8")
    rules = nested / ".mao" / "rules"
    rules.mkdir(parents=True)
    (rules / "python.md").write_text("feature rule", encoding="utf-8")

    bundle = ProjectRuleResolver().resolve(str(nested), cwd=tmp_path)

    assert [source.content for source in bundle.sources] == [
        "root rule",
        "src rule",
        "feature rule",
    ]
    assert bundle.project_root == str(tmp_path)
    assert bundle.target_dir == str(nested)
    assert "不能覆盖系统安全约束" in bundle.prompt()


def test_supports_compatibility_rule_directories(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    expected = []
    for relative in (".grok/rules", ".claude/rules", ".cursor/rules"):
        directory = tmp_path / relative
        directory.mkdir(parents=True)
        content = f"rule from {relative}"
        (directory / "rule.md").write_text(content, encoding="utf-8")
        expected.append(content)

    bundle = ProjectRuleResolver().resolve(cwd=tmp_path)

    assert [source.content for source in bundle.sources] == expected
    assert {source.origin for source in bundle.sources} == {
        "grok-compatible",
        "claude-compatible",
        "cursor-compatible",
    }


def test_deduplicates_case_variant_rule_names(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    (tmp_path / "AGENTS.md").write_text("one rule", encoding="utf-8")

    bundle = ProjectRuleResolver().resolve(cwd=tmp_path)

    assert len(bundle.sources) == 1


def test_enforces_per_file_and_total_limits(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    (tmp_path / "AGENTS.md").write_text("a" * 20, encoding="utf-8")
    rules = tmp_path / ".mao" / "rules"
    rules.mkdir(parents=True)
    (rules / "a.md").write_text("b" * 20, encoding="utf-8")

    bundle = ProjectRuleResolver(max_chars_per_file=8, max_total_chars=12).resolve(cwd=tmp_path)

    assert bundle.total_chars == 12
    assert bundle.truncated is True
    assert [source.chars for source in bundle.sources] == [8, 4]
    assert all(source.truncated for source in bundle.sources)


def test_uses_explicit_existing_request_path(tmp_path: Path):
    project = tmp_path / "external"
    project.mkdir()
    (project / "AGENTS.md").write_text("external rule", encoding="utf-8")

    bundle = ProjectRuleResolver().resolve(
        f"please inspect {project}", cwd=tmp_path / "unrelated"
    )

    assert bundle.target_dir == str(project)
    assert [source.content for source in bundle.sources] == ["external rule"]


def test_agent_records_and_injects_project_rules(tmp_path: Path, monkeypatch):
    from unittest.mock import MagicMock

    from src.core.agent import Agent
    from src.core.session import Session

    monkeypatch.chdir(tmp_path)
    (tmp_path / ".git").mkdir()
    (tmp_path / "AGENTS.md").write_text("always run focused tests", encoding="utf-8")
    session = Session(
        id="rules",
        created_at="2026-07-18T00:00:00+00:00",
        updated_at="2026-07-18T00:00:00+00:00",
        output_dir=str(tmp_path / "sessions" / "rules" / "output"),
    )
    gateway = MagicMock()
    gateway.get_main_model.return_value = "main"
    gateway.resolve_model.return_value = "main"
    agent = Agent(gateway, session)

    journal = agent._start_engineering_run("review this project")
    prompt = agent._build_system_prompt("review this project", journal.intent)

    assert "always run focused tests" in prompt
    assert journal.rule_context["source_count"] == 1
    assert journal.rule_context["sources"][0]["path"].endswith("AGENTS.md")
