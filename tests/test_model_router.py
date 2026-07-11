"""模型路由单元测试"""
import pytest

from src.gateway.router import ModelRouter
from src.models.schemas import ModelConfig, Task


def _sample_models() -> dict[str, ModelConfig]:
    return {
        "glm-ark": ModelConfig(provider="ark", model_id="ark-code-latest"),
        "claude-sonnet-5": ModelConfig(provider="anthropic", model_id="claude-sonnet-5-20251001"),
        "claude-haiku-4-5": ModelConfig(provider="anthropic", model_id="claude-haiku-4-5-20251001"),
    }


def _default_routing() -> dict[str, str]:
    return {
        "frontend": "claude-sonnet-5",
        "backend": "glm-ark",
        "test": "claude-haiku-4-5",
    }


def test_resolve_model_by_assigned_model():
    router = ModelRouter(_sample_models(), _default_routing())
    task = Task(id="t1", type="backend", title="API", input="", assigned_model="glm-ark")

    config = router.resolve_model(task)
    assert config.provider == "ark"
    assert config.model_id == "ark-code-latest"


def test_resolve_model_fallback_to_default_routing():
    router = ModelRouter(_sample_models(), _default_routing())
    task = Task(id="t1", type="frontend", title="UI", input="", assigned_model="")

    config = router.resolve_model(task)
    assert config.provider == "anthropic"
    assert config.model_id == "claude-sonnet-5-20251001"


def test_resolve_model_fallback_when_assigned_model_unknown():
    router = ModelRouter(_sample_models(), _default_routing())
    task = Task(id="t1", type="test", title="Test", input="", assigned_model="unknown-model")

    config = router.resolve_model(task)
    assert config.provider == "anthropic"
    assert config.model_id == "claude-haiku-4-5-20251001"


def test_resolve_model_raises_when_unresolvable():
    router = ModelRouter(_sample_models(), _default_routing())
    task = Task(id="t1", type="unknown_type", title="X", input="", assigned_model="also-unknown")

    with pytest.raises(ValueError, match="无法为任务"):
        router.resolve_model(task)


def test_list_models_returns_keys():
    router = ModelRouter(_sample_models(), _default_routing())
    assert set(router.list_models()) == {"glm-ark", "claude-sonnet-5", "claude-haiku-4-5"}
