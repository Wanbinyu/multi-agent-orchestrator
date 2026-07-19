from unittest.mock import MagicMock

from src.core.planning_council import PlanningCouncil
from src.models.schemas import ChatResponse


def test_planning_council_uses_four_readonly_roles(tmp_path):
    config = tmp_path / "workers.yaml"
    config.write_text(
        """
orchestrator: {model: planner}
reviewer: {model: reviewer}
available_workers:
  continuity_checker: {default_model: recon}
  architect: {default_model: architect}
  editor: {default_model: critic}
""",
        encoding="utf-8",
    )
    gateway = MagicMock()
    gateway.get_main_model.return_value = "main"
    gateway.resolve_model.side_effect = lambda model: model
    gateway.chat.side_effect = [
        ChatResponse(content="evidence gaps", model="recon", provider="test", input_tokens=1, output_tokens=2),
        ChatResponse(content="architecture plan", model="architect", provider="test", input_tokens=3, output_tokens=4),
        ChatResponse(content="critical risks", model="critic", provider="test", input_tokens=5, output_tokens=6),
        ChatResponse(content="final bounded plan", model="main", provider="test", input_tokens=7, output_tokens=8),
    ]

    result = PlanningCouncil(
        gateway,
        config_path=str(config),
        project_rules="RULE SENTINEL",
        permission_context={"rules": ["deny writes"]},
    ).refine("objective", "draft", "tool evidence")

    assert result.content == "final bounded plan"
    assert [role["role"] for role in result.roles] == [
        "reconnaissance", "architect", "critic", "synthesizer"
    ]
    assert result.input_tokens == 16
    assert result.output_tokens == 20
    assert all("tools" not in call.kwargs for call in gateway.chat.call_args_list)
    assert "RULE SENTINEL" in gateway.chat.call_args_list[0].kwargs["messages"][1].content


def test_planning_council_keeps_draft_when_roles_fail(tmp_path):
    gateway = MagicMock()
    gateway.get_main_model.return_value = "main"
    gateway.resolve_model.side_effect = RuntimeError("offline")

    result = PlanningCouncil(gateway, config_path=str(tmp_path / "missing.yaml")).refine(
        "objective", "stable draft"
    )

    assert result.content == "stable draft"
    assert len(result.diagnostics) == 4
