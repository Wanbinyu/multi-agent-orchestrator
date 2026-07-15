"""内置模型目录

为常见中文/国际模型服务提供默认配置，降低用户配置门槛。
设计参考 OpenCode 的 models.dev 目录：每个模型包含标识、能力、默认上游 ID。
"""
from __future__ import annotations

from typing import Any


class ModelCatalogEntry:
    """目录中的模型条目"""

    def __init__(
        self,
        alias: str,
        name: str,
        provider_type: str,
        default_model_id: str,
        capabilities: list[str] | None = None,
        input_price_per_1m: float = 0.0,
        output_price_per_1m: float = 0.0,
        description: str = "",
        context_window_tokens: int = 0,
        max_output_tokens: int = 4096,
        context_window_source: str = "unverified",
        context_window_verified_at: str = "",
        dynamic_model_alias: bool = False,
    ):
        self.alias = alias
        self.name = name
        self.provider_type = provider_type
        self.default_model_id = default_model_id
        self.capabilities = capabilities or []
        self.input_price_per_1m = input_price_per_1m
        self.output_price_per_1m = output_price_per_1m
        self.description = description
        self.context_window_tokens = context_window_tokens
        self.max_output_tokens = max_output_tokens
        self.context_window_source = context_window_source
        self.context_window_verified_at = context_window_verified_at
        self.dynamic_model_alias = dynamic_model_alias

    def to_model_config(self, provider_name: str) -> dict[str, Any]:
        """生成 providers.yaml 中 models 段的配置"""
        return {
            "provider": provider_name,
            "model_id": self.default_model_id,
            "input_price_per_1m": self.input_price_per_1m,
            "output_price_per_1m": self.output_price_per_1m,
            "capabilities": self.capabilities,
            "context_window_tokens": self.context_window_tokens,
            "max_output_tokens": self.max_output_tokens,
            "context_window_source": self.context_window_source,
            "context_window_verified_at": self.context_window_verified_at,
            "dynamic_model_alias": self.dynamic_model_alias,
        }


# 内置模型目录
# 价格仅为占位，实际以各平台最新为准
BUILTIN_MODELS: dict[str, ModelCatalogEntry] = {
    "glm-ark": ModelCatalogEntry(
        alias="glm-ark",
        name="火山方舟 Coding",
        provider_type="anthropic",
        default_model_id="ark-code-latest",
        capabilities=["tool_use", "coding", "reasoning"],
        input_price_per_1m=1.0,
        output_price_per_1m=1.0,
        description="火山方舟 Coding Plan，兼容 Anthropic Messages API",
        context_window_source="unverified_dynamic_alias",
        dynamic_model_alias=True,
    ),
    "glm-chat": ModelCatalogEntry(
        alias="glm-chat",
        name="火山方舟 Chat",
        provider_type="anthropic",
        default_model_id="ark-chat-latest",
        capabilities=["tool_use", "chat"],
        input_price_per_1m=1.0,
        output_price_per_1m=1.0,
        description="火山方舟 Chat，兼容 Anthropic Messages API",
        context_window_source="unverified_dynamic_alias",
        dynamic_model_alias=True,
    ),
    "kimi-for-coding": ModelCatalogEntry(
        alias="kimi-for-coding",
        name="Kimi Coding",
        provider_type="openai",
        default_model_id="kimi-for-coding",
        capabilities=["tool_use", "coding"],
        input_price_per_1m=1.0,
        output_price_per_1m=1.0,
        description="Kimi 编码模型，OpenAI 兼容接口",
    ),
    "deepseek-chat": ModelCatalogEntry(
        alias="deepseek-chat",
        name="DeepSeek Chat",
        provider_type="openai",
        default_model_id="deepseek-chat",
        capabilities=["tool_use", "chat", "reasoning"],
        input_price_per_1m=0.5,
        output_price_per_1m=2.0,
        description="DeepSeek V3 Chat，OpenAI 兼容接口",
    ),
    "deepseek-reasoner": ModelCatalogEntry(
        alias="deepseek-reasoner",
        name="DeepSeek Reasoner",
        provider_type="openai",
        default_model_id="deepseek-reasoner",
        capabilities=["reasoning"],
        input_price_per_1m=0.5,
        output_price_per_1m=2.0,
        description="DeepSeek R1，适合复杂推理",
    ),
    "claude-opus-4-8": ModelCatalogEntry(
        alias="claude-opus-4-8",
        name="Claude Opus 4.8",
        provider_type="anthropic",
        default_model_id="claude-opus-4-8-20251001",
        capabilities=["tool_use", "coding", "reasoning", "vision"],
        input_price_per_1m=15.0,
        output_price_per_1m=75.0,
        description="Anthropic Claude Opus，最强推理",
    ),
    "claude-sonnet-5": ModelCatalogEntry(
        alias="claude-sonnet-5",
        name="Claude Sonnet 5",
        provider_type="anthropic",
        default_model_id="claude-sonnet-5-20251001",
        capabilities=["tool_use", "coding", "reasoning", "vision"],
        input_price_per_1m=3.0,
        output_price_per_1m=15.0,
        description="Anthropic Claude Sonnet，均衡选择",
    ),
    "claude-haiku-4-5": ModelCatalogEntry(
        alias="claude-haiku-4-5",
        name="Claude Haiku 4.5",
        provider_type="anthropic",
        default_model_id="claude-haiku-4-5-20251001",
        capabilities=["tool_use", "chat"],
        input_price_per_1m=0.5,
        output_price_per_1m=2.0,
        description="Anthropic Claude Haiku，快速便宜",
    ),
    "gpt-4o": ModelCatalogEntry(
        alias="gpt-4o",
        name="GPT-4o",
        provider_type="openai",
        default_model_id="gpt-4o",
        capabilities=["tool_use", "coding", "vision"],
        input_price_per_1m=5.0,
        output_price_per_1m=15.0,
        description="OpenAI GPT-4o",
    ),
    "gpt-4o-mini": ModelCatalogEntry(
        alias="gpt-4o-mini",
        name="GPT-4o Mini",
        provider_type="openai",
        default_model_id="gpt-4o-mini",
        capabilities=["tool_use", "chat"],
        input_price_per_1m=0.15,
        output_price_per_1m=0.6,
        description="OpenAI GPT-4o Mini，经济实惠",
    ),
}

# Provider 类型预定义模板
PROVIDER_TEMPLATES: dict[str, dict[str, Any]] = {
    "volcengine_ark": {
        "name": "火山方舟",
        "type": "anthropic",
        "base_url": "https://ark.cn-beijing.volces.com/api/coding",
        "timeout": 120,
        "rpm_limit": 60,
        "supported_models": ["glm-ark", "glm-chat"],
    },
    "openai": {
        "name": "OpenAI",
        "type": "openai",
        "base_url": "https://api.openai.com/v1",
        "timeout": 120,
        "rpm_limit": 60,
        "supported_models": ["gpt-4o", "gpt-4o-mini"],
    },
    "anthropic": {
        "name": "Anthropic",
        "type": "anthropic",
        "base_url": "https://api.anthropic.com",
        "timeout": 120,
        "rpm_limit": 60,
        "supported_models": ["claude-opus-4-8", "claude-sonnet-5", "claude-haiku-4-5"],
    },
    "kimi": {
        "name": "Kimi 转发",
        "type": "openai",
        "base_url": "https://api.moonshot.cn/v1",
        "timeout": 120,
        "rpm_limit": 60,
        "supported_models": ["kimi-for-coding"],
    },
    "deepseek": {
        "name": "DeepSeek",
        "type": "openai",
        "base_url": "https://api.deepseek.com/v1",
        "timeout": 120,
        "rpm_limit": 60,
        "supported_models": ["deepseek-chat", "deepseek-reasoner"],
    },
    "custom_openai": {
        "name": "自定义 OpenAI 兼容服务",
        "type": "openai",
        "base_url": "",
        "timeout": 120,
        "rpm_limit": 60,
        "supported_models": [],
    },
}


def get_model_catalog() -> dict[str, ModelCatalogEntry]:
    """获取内置模型目录"""
    return BUILTIN_MODELS.copy()


def get_provider_templates() -> dict[str, dict[str, Any]]:
    """获取 Provider 模板"""
    return PROVIDER_TEMPLATES.copy()


def list_models_by_provider(provider_type: str) -> list[ModelCatalogEntry]:
    """按 Provider 类型列出支持的模型"""
    return [m for m in BUILTIN_MODELS.values() if m.provider_type == provider_type]


def find_models_for_template(template_key: str) -> list[ModelCatalogEntry]:
    """根据 Provider 模板找出推荐的模型列表"""
    template = PROVIDER_TEMPLATES.get(template_key)
    if not template:
        return []
    aliases = template.get("supported_models", [])
    return [BUILTIN_MODELS[a] for a in aliases if a in BUILTIN_MODELS]


def get_default_model_for_template(template_key: str) -> str | None:
    """获取某个 Provider 模板的默认模型别名"""
    models = find_models_for_template(template_key)
    return models[0].alias if models else None
