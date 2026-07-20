"""B5.3 explainable model-routing contract tests."""
from __future__ import annotations

from unittest.mock import MagicMock

from src.core.agent import Agent
from src.core.engineering import RunJournalStore
from src.core.session import Session
from src.gateway.router import ModelRouter
from src.models.schemas import (
    ChatResponse,
    ModelConfig,
    ModelRoutingConstraints,
)


def _config(
    model_id: str,
    *,
    capabilities: dict[str, str] | None = None,
    source: str = "provider_docs",
    input_price: float = 1.0,
    output_price: float = 1.0,
    context: int = 128_000,
) -> ModelConfig:
    return ModelConfig(
        provider="provider",
        model_id=model_id,
        capability_status=capabilities or {},
        metadata_source=source,
        input_price_per_1m=input_price,
        output_price_per_1m=output_price,
        context_window_tokens=context,
        context_window_source="provider_docs",
    )


def _route(
    models: dict[str, ModelConfig],
    *,
    requested: str = "main",
    mode: str = "auto",
    task_kind: str = "change",
    depth: str = "standard",
    unhealthy: set[str] | None = None,
    local: set[str] | None = None,
    estimated_input: int = 4_000,
):
    return ModelRouter(models, {}).route(
        task_kind=task_kind,
        execution_depth=depth,
        constraints=ModelRoutingConstraints(
            mode=mode,
            requested_model=requested,
        ),
        estimated_input_tokens=estimated_input,
        unhealthy_models=unhealthy,
        local_models=local,
    )


def test_fixed_mode_keeps_user_model_even_when_another_scores_higher():
    decision = _route(
        {
            "main": _config(
                "main", capabilities={"coding": "unverified"}, input_price=10
            ),
            "candidate": _config(
                "candidate", capabilities={"coding": "supported"}, input_price=1
            ),
        },
        mode="fixed",
    )

    assert decision.selected_model == "main"
    assert decision.source == "user_fixed"
    assert decision.upgrade_count == 0


def test_verified_capability_can_select_one_automatic_upgrade():
    decision = _route(
        {
            "main": _config("main", capabilities={"coding": "unverified"}),
            "candidate": _config(
                "candidate", capabilities={"coding": "supported"}
            ),
        }
    )

    assert decision.selected_model == "candidate"
    assert decision.source == "automatic"
    assert decision.required_capabilities == ["coding"]
    assert decision.upgrade_count == 1
    assert decision.max_upgrades == 1
    assert "已验证能力" in decision.reason


def test_legacy_unverified_capability_list_cannot_trigger_upgrade():
    main = _config("main", capabilities={"coding": "supported"})
    candidate = ModelConfig(
        provider="provider",
        model_id="candidate",
        capabilities=["coding"],
        metadata_source="unverified",
        input_price_per_1m=0.1,
        output_price_per_1m=0.1,
    )

    decision = _route({"main": main, "candidate": candidate})
    evaluated = next(item for item in decision.candidates if item.model == "candidate")

    assert decision.selected_model == "main"
    assert evaluated.eligible is False
    assert evaluated.capability_states["coding"] == "unverified"


def test_unknown_price_never_allows_savings_claim():
    decision = _route(
        {
            "main": _config("main", capabilities={"coding": "unverified"}),
            "candidate": _config(
                "candidate",
                capabilities={"coding": "supported"},
                source="unverified",
                input_price=0.0,
                output_price=0.0,
            ),
        }
    )

    assert decision.selected_model == "candidate"
    assert decision.price_comparison == "unknown"
    assert decision.savings_claim_allowed is False
    assert "省" not in decision.reason


def test_verified_lower_cost_can_route_fast_task():
    decision = _route(
        {
            "main": _config(
                "main",
                capabilities={"chat": "supported"},
                input_price=10,
                output_price=20,
            ),
            "cheap": _config(
                "cheap",
                capabilities={"chat": "supported"},
                input_price=0.1,
                output_price=0.2,
            ),
        },
        task_kind="answer",
        depth="fast",
    )

    assert decision.selected_model == "cheap"
    assert decision.price_comparison == "cheaper"
    assert decision.savings_claim_allowed is True
    assert "更低估算成本" in decision.reason


def test_answer_does_not_choose_cheaper_model_without_verified_chat():
    decision = _route(
        {
            "main": _config(
                "main",
                capabilities={"chat": "supported"},
                input_price=10,
                output_price=20,
            ),
            "coding-only": _config(
                "coding-only",
                capabilities={"coding": "supported"},
                input_price=0.1,
                output_price=0.2,
            ),
        },
        task_kind="answer",
        depth="fast",
    )

    candidate = next(
        item for item in decision.candidates if item.model == "coding-only"
    )
    assert decision.selected_model == "main"
    assert candidate.capability_states["chat"] == "unverified"
    assert candidate.eligible is False


def test_unclassified_task_does_not_optimize_model_without_failure():
    decision = _route(
        {
            "main": _config("main", input_price=10, output_price=20),
            "cheap": _config("cheap", input_price=0.1, output_price=0.2),
        },
        task_kind="unclassified",
        depth="standard",
    )

    assert decision.selected_model == "main"
    assert decision.source == "user_fallback"


def test_health_and_context_are_hard_candidate_filters():
    models = {
        "main": _config("main", capabilities={"coding": "supported"}),
        "healthy": _config("healthy", capabilities={"coding": "supported"}),
    }
    unhealthy = _route(models, unhealthy={"main"})

    assert unhealthy.selected_model == "healthy"
    assert "健康冷却期" in unhealthy.reason

    tiny_main = _config(
        "tiny", capabilities={"coding": "supported"}, context=8_000
    )
    roomy = _config(
        "roomy", capabilities={"coding": "supported"}, context=128_000
    )
    context = _route(
        {"tiny": tiny_main, "roomy": roomy},
        requested="tiny",
        estimated_input=10_000,
    )

    assert context.selected_model == "roomy"
    assert "上下文预算不足" in context.reason


def test_fast_prefers_verified_healthy_zero_marginal_local_model():
    decision = _route(
        {
            "cloud": _config(
                "cloud",
                capabilities={"chat": "supported"},
                input_price=2,
                output_price=8,
            ),
            "local": _config(
                "local",
                capabilities={"chat": "supported"},
                source="local_runtime_config",
                input_price=99,
                output_price=99,
            ),
        },
        requested="cloud",
        task_kind="answer",
        depth="fast",
        local={"local"},
    )

    local = next(item for item in decision.candidates if item.model == "local")
    assert decision.selected_model == "local"
    assert decision.price_comparison == "cheaper"
    assert decision.savings_claim_allowed is True
    assert local.local is True
    assert local.price_known is True
    assert local.estimated_cost_usd == 0.0


def test_local_cost_bonus_never_bypasses_health_capability_or_context():
    cloud = _config("cloud", capabilities={"coding": "supported"})
    unverified = _config(
        "local", capabilities={"coding": "unverified"}, context=8_000
    )

    unhealthy = _route(
        {"cloud": cloud, "local": _config("local", capabilities={"coding": "supported"})},
        requested="cloud",
        depth="fast",
        local={"local"},
        unhealthy={"local"},
    )
    unknown_capability = _route(
        {"cloud": cloud, "local": unverified},
        requested="cloud",
        depth="fast",
        local={"local"},
    )
    too_small = _route(
        {
            "cloud": cloud,
            "local": _config("local", capabilities={"coding": "supported"}, context=8_000),
        },
        requested="cloud",
        depth="fast",
        local={"local"},
        estimated_input=10_000,
    )

    assert unhealthy.selected_model == "cloud"
    assert unknown_capability.selected_model == "cloud"
    assert too_small.selected_model == "cloud"
    assert any(
        "健康冷却期" in reason
        for reason in next(
            item for item in unhealthy.candidates if item.model == "local"
        ).reasons
    )
    assert any(
        "unverified" in reason
        for reason in next(
            item for item in unknown_capability.candidates if item.model == "local"
        ).reasons
    )
    assert any(
        "安全输入预算不足" in reason
        for reason in next(
            item for item in too_small.candidates if item.model == "local"
        ).reasons
    )


def test_deep_coding_requires_reasoning_before_local_cost_is_considered():
    decision = _route(
        {
            "local": _config(
                "local", capabilities={"coding": "supported", "reasoning": "unverified"}
            ),
            "cloud": _config(
                "cloud", capabilities={"coding": "supported", "reasoning": "supported"}
            ),
        },
        requested="local",
        task_kind="build",
        depth="deep",
        local={"local"},
    )

    assert decision.selected_model == "cloud"
    assert "reasoning" in decision.required_capabilities


def _gateway(models: dict[str, ModelConfig], main_model: str) -> MagicMock:
    gateway = MagicMock()
    gateway.models = models
    gateway.main_model = main_model
    gateway.router = ModelRouter(models, {})
    gateway._unhealthy_models = {}
    provider = MagicMock()
    provider.config.type = "openai"
    gateway.providers = {"provider": provider}
    gateway.get_model_config.side_effect = lambda alias: models[alias]
    gateway.chat.return_value = ChatResponse(
        content="完成分析",
        model="candidate-id",
        provider="provider",
        input_tokens=10,
        output_tokens=5,
    )
    gateway.last_attempt_trace = []
    return gateway


def test_agent_uses_selected_model_and_journals_full_decision(tmp_path):
    models = {
        "main": _config("main-id", capabilities={"coding": "unverified"}),
        "candidate": _config(
            "candidate-id", capabilities={"coding": "supported"}
        ),
    }
    gateway = _gateway(models, "main")
    session = Session(
        id="routing-session",
        created_at="2026-07-19T00:00:00+00:00",
        updated_at="2026-07-19T00:00:00+00:00",
        output_dir=str(tmp_path / "session" / "output"),
    )

    result = Agent(gateway, session).run_turn("修复 CLI 输出")
    journal = RunJournalStore.from_output_dir(session.output_dir).load(result.run_id)

    assert gateway.chat.call_args.args[1] == "candidate"
    gateway.chat_with_main_model.assert_not_called()
    assert journal.version == 5
    assert journal.model_routing is not None
    assert journal.model_routing.selected_model == "candidate"
    assert len(journal.model_routing.candidates) == 2
    assert result.engineering["model_routing"]["selected_model"] == "candidate"


def test_agent_fixed_mode_uses_main_model(tmp_path):
    models = {
        "main": _config("main-id", capabilities={"coding": "unverified"}),
        "candidate": _config(
            "candidate-id", capabilities={"coding": "supported"}
        ),
    }
    gateway = _gateway(models, "main")
    session = Session(
        id="fixed-session",
        created_at="2026-07-19T00:00:00+00:00",
        updated_at="2026-07-19T00:00:00+00:00",
        output_dir=str(tmp_path / "session" / "output"),
        model_routing_mode="fixed",
    )

    result = Agent(gateway, session).run_turn("修复 CLI 输出")

    assert gateway.chat.call_args.args[1] == "main"
    assert result.engineering["model_routing"]["source"] == "user_fixed"
