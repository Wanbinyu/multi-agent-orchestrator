"""O3：Provider 兼容矩阵与 catalog / 路由 / 错误码合同。"""
from __future__ import annotations

from src.gateway.errors import _ERROR_DETAILS
from src.gateway.router import ModelRouter
from src.models.catalog import (
    BUILTIN_MODELS,
    PROVIDER_TEMPLATES,
    export_compatibility_matrix,
    is_verified_metadata_source,
)
from src.models.schemas import ModelConfig, ModelRoutingConstraints


def test_export_matrix_covers_every_catalog_entry():
    rows = export_compatibility_matrix()
    aliases = {row["alias"] for row in rows}
    assert aliases == set(BUILTIN_MODELS)
    assert len(rows) == len(BUILTIN_MODELS)


def test_supported_capability_requires_verified_metadata_source():
    """已验证能力不得挂在 unverified 元数据上来源上。"""
    for row in export_compatibility_matrix():
        if row["routing_eligible_capabilities"]:
            assert row["metadata_verified"], (
                f"{row['alias']} 将 {row['routing_eligible_capabilities']} "
                f"标为 supported，但 metadata_source={row['metadata_source']!r}"
            )


def test_unverified_entries_have_no_routing_eligible_capabilities():
    for row in export_compatibility_matrix():
        if not row["metadata_verified"]:
            assert row["routing_eligible_capabilities"] == [], row["alias"]
            assert row["price_is_placeholder"] is True


def test_template_models_exist_and_appear_in_matrix():
    matrix_aliases = {row["alias"] for row in export_compatibility_matrix()}
    for key, template in PROVIDER_TEMPLATES.items():
        for alias in template.get("supported_models", []):
            assert alias in BUILTIN_MODELS, f"{key}: missing {alias}"
            assert alias in matrix_aliases


def test_matrix_template_keys_match_provider_templates():
    for row in export_compatibility_matrix():
        for key in row["template_keys"]:
            assert key in PROVIDER_TEMPLATES
            assert row["alias"] in PROVIDER_TEMPLATES[key]["supported_models"]


def test_all_provider_error_codes_have_user_facing_details():
    # ProviderErrorCode 是 Literal 联合；从 _ERROR_DETAILS 键与注解保持一致
    codes = set(_ERROR_DETAILS)
    expected = {
        "configuration_error",
        "authentication_error",
        "permission_error",
        "model_not_found",
        "quota_exceeded",
        "rate_limit_error",
        "timeout_error",
        "connection_error",
        "server_error",
        "context_length_error",
        "invalid_request_error",
        "stream_interrupted",
        "provider_error",
    }
    assert codes == expected
    for code, (message, action, retryable, failover) in _ERROR_DETAILS.items():
        assert message.strip(), code
        assert action.strip(), code
        assert isinstance(retryable, bool)
        assert isinstance(failover, bool)


def test_auth_and_config_errors_do_not_failover():
    assert _ERROR_DETAILS["authentication_error"][3] is False
    assert _ERROR_DETAILS["configuration_error"][3] is False
    assert _ERROR_DETAILS["permission_error"][3] is False
    assert _ERROR_DETAILS["rate_limit_error"][2] is True
    assert _ERROR_DETAILS["quota_exceeded"][2] is False


def test_router_rejects_unverified_capability_for_automatic_upgrade():
    models = {
        "main": ModelConfig(
            provider="p",
            model_id="main",
            capability_status={"coding": "unverified"},
            metadata_source="unverified",
            input_price_per_1m=1.0,
            output_price_per_1m=1.0,
            context_window_tokens=128_000,
            context_window_source="provider_docs",
        ),
        "better": ModelConfig(
            provider="p",
            model_id="better",
            capability_status={"coding": "unverified"},
            metadata_source="unverified",
            input_price_per_1m=0.1,
            output_price_per_1m=0.1,
            context_window_tokens=128_000,
            context_window_source="provider_docs",
        ),
    }
    decision = ModelRouter(models, {}).route(
        task_kind="change",
        execution_depth="standard",
        constraints=ModelRoutingConstraints(mode="auto", requested_model="main"),
        estimated_input_tokens=1000,
    )
    assert decision.selected_model == "main"
    better = next(c for c in decision.candidates if c.model == "better")
    assert better.eligible is False
    assert better.capability_states["coding"] == "unverified"


def test_is_verified_metadata_source_matches_router_policy():
    assert is_verified_metadata_source(
        "https://platform.claude.com/docs/en/about-claude/models/overview"
    )
    assert not is_verified_metadata_source("unverified")
    assert not is_verified_metadata_source("unverified_press_2026-07")
    assert not is_verified_metadata_source("unknown")
    assert not is_verified_metadata_source("")
