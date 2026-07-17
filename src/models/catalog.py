"""内置模型目录

为常见中文/国际模型服务提供默认配置，降低用户配置门槛。
设计参考 OpenCode 的 models.dev 目录：每个模型包含标识、能力、默认上游 ID。
"""
from __future__ import annotations

from typing import Any

from src.models.schemas import CapabilityState


_CAPABILITY_STATES = {"supported", "unsupported", "unverified"}
_ANTHROPIC_MODEL_SOURCE = "https://platform.claude.com/docs/en/about-claude/models/overview"
_ANTHROPIC_VERIFIED_AT = "2026-07-16"


class ModelCatalogEntry:
    """目录中的模型条目"""

    def __init__(
        self,
        alias: str,
        name: str,
        provider_type: str,
        default_model_id: str,
        capabilities: list[str] | None = None,
        capability_status: dict[str, CapabilityState] | None = None,
        input_price_per_1m: float = 0.0,
        output_price_per_1m: float = 0.0,
        description: str = "",
        context_window_tokens: int = 0,
        max_output_tokens: int = 4096,
        context_window_source: str = "unverified",
        context_window_verified_at: str = "",
        dynamic_model_alias: bool = False,
        metadata_source: str = "unverified",
        metadata_verified_at: str = "",
    ):
        self.alias = alias
        self.name = name
        self.provider_type = provider_type
        self.default_model_id = default_model_id
        self.capabilities = list(capabilities or [])
        self.capability_status = dict(capability_status) if capability_status else {
            capability: "unverified" for capability in self.capabilities
        }
        invalid_states = set(self.capability_status.values()) - _CAPABILITY_STATES
        if invalid_states:
            raise ValueError(f"无效能力状态: {sorted(invalid_states)}")
        if not metadata_source.strip():
            raise ValueError("metadata_source 不能为空")
        self.input_price_per_1m = input_price_per_1m
        self.output_price_per_1m = output_price_per_1m
        self.description = description
        self.context_window_tokens = context_window_tokens
        self.max_output_tokens = max_output_tokens
        self.context_window_source = context_window_source
        self.context_window_verified_at = context_window_verified_at
        self.dynamic_model_alias = dynamic_model_alias
        self.metadata_source = metadata_source.strip()
        self.metadata_verified_at = metadata_verified_at

    def to_model_data(self) -> dict[str, Any]:
        """生成不含 Provider 归属的模型配置。"""
        return {
            "model_id": self.default_model_id,
            "input_price_per_1m": self.input_price_per_1m,
            "output_price_per_1m": self.output_price_per_1m,
            "capabilities": list(self.capabilities),
            "capability_status": dict(self.capability_status),
            "metadata_source": self.metadata_source,
            "metadata_verified_at": self.metadata_verified_at,
            "context_window_tokens": self.context_window_tokens,
            "max_output_tokens": self.max_output_tokens,
            "context_window_source": self.context_window_source,
            "context_window_verified_at": self.context_window_verified_at,
            "dynamic_model_alias": self.dynamic_model_alias,
        }

    def to_model_config(self, provider_name: str) -> dict[str, Any]:
        """生成 providers.yaml 中 models 段的配置。"""
        return {"provider": provider_name, **self.to_model_data()}


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
    "claude-fable-5": ModelCatalogEntry(
        alias="claude-fable-5",
        name="Claude Fable 5",
        provider_type="anthropic",
        default_model_id="claude-fable-5",
        capabilities=["tool_use", "coding", "reasoning", "vision"],
        capability_status={
            "tool_use": "unverified",
            "coding": "supported",
            "reasoning": "supported",
            "vision": "unverified",
        },
        input_price_per_1m=10.0,
        output_price_per_1m=50.0,
        description="Anthropic Claude Fable，长时 Agent 能力",
        context_window_tokens=1_000_000,
        max_output_tokens=128_000,
        context_window_source=_ANTHROPIC_MODEL_SOURCE,
        context_window_verified_at=_ANTHROPIC_VERIFIED_AT,
        metadata_source=_ANTHROPIC_MODEL_SOURCE,
        metadata_verified_at=_ANTHROPIC_VERIFIED_AT,
    ),
    "claude-opus-4-8": ModelCatalogEntry(
        alias="claude-opus-4-8",
        name="Claude Opus 4.8",
        provider_type="anthropic",
        default_model_id="claude-opus-4-8",
        capabilities=["tool_use", "coding", "reasoning", "vision"],
        capability_status={
            "tool_use": "unverified",
            "coding": "supported",
            "reasoning": "supported",
            "vision": "unverified",
        },
        input_price_per_1m=5.0,
        output_price_per_1m=25.0,
        description="Anthropic Claude Opus，最强推理",
        context_window_tokens=1_000_000,
        max_output_tokens=128_000,
        context_window_source=_ANTHROPIC_MODEL_SOURCE,
        context_window_verified_at=_ANTHROPIC_VERIFIED_AT,
        metadata_source=_ANTHROPIC_MODEL_SOURCE,
        metadata_verified_at=_ANTHROPIC_VERIFIED_AT,
    ),
    "claude-sonnet-5": ModelCatalogEntry(
        alias="claude-sonnet-5",
        name="Claude Sonnet 5",
        provider_type="anthropic",
        default_model_id="claude-sonnet-5",
        capabilities=["tool_use", "coding", "reasoning", "vision"],
        capability_status={
            "tool_use": "unverified",
            "coding": "supported",
            "reasoning": "supported",
            "vision": "unverified",
        },
        input_price_per_1m=3.0,
        output_price_per_1m=15.0,
        description="Anthropic Claude Sonnet，均衡选择",
        context_window_tokens=1_000_000,
        max_output_tokens=128_000,
        context_window_source=_ANTHROPIC_MODEL_SOURCE,
        context_window_verified_at=_ANTHROPIC_VERIFIED_AT,
        metadata_source=_ANTHROPIC_MODEL_SOURCE,
        metadata_verified_at=_ANTHROPIC_VERIFIED_AT,
    ),
    "claude-haiku-4-5": ModelCatalogEntry(
        alias="claude-haiku-4-5",
        name="Claude Haiku 4.5",
        provider_type="anthropic",
        default_model_id="claude-haiku-4-5-20251001",
        capabilities=["tool_use", "chat", "reasoning", "vision"],
        capability_status={
            "tool_use": "unverified",
            "chat": "supported",
            "reasoning": "supported",
            "vision": "unverified",
        },
        input_price_per_1m=1.0,
        output_price_per_1m=5.0,
        description="Anthropic Claude Haiku，快速便宜",
        context_window_tokens=200_000,
        max_output_tokens=64_000,
        context_window_source=_ANTHROPIC_MODEL_SOURCE,
        context_window_verified_at=_ANTHROPIC_VERIFIED_AT,
        metadata_source=_ANTHROPIC_MODEL_SOURCE,
        metadata_verified_at=_ANTHROPIC_VERIFIED_AT,
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
    # 2026-07 扩充：覆盖主流 Provider。元数据未逐项核实的条目保持
    # metadata_source="unverified"，价格仅为占位，实际以各平台最新为准。
    "gpt-5": ModelCatalogEntry(
        alias="gpt-5",
        name="GPT-5",
        provider_type="openai",
        default_model_id="gpt-5",
        capabilities=["tool_use", "coding", "reasoning", "vision"],
        input_price_per_1m=5.0,
        output_price_per_1m=15.0,
        description="OpenAI GPT-5",
    ),
    "deepseek-v4-pro": ModelCatalogEntry(
        alias="deepseek-v4-pro",
        name="DeepSeek V4 Pro",
        provider_type="openai",
        default_model_id="deepseek-v4-pro",
        capabilities=["coding", "reasoning"],
        input_price_per_1m=1.0,
        output_price_per_1m=4.0,
        description="DeepSeek V4 Pro，编程与推理",
    ),
    "deepseek-v4-flash": ModelCatalogEntry(
        alias="deepseek-v4-flash",
        name="DeepSeek V4 Flash",
        provider_type="openai",
        default_model_id="deepseek-v4-flash",
        capabilities=["coding", "chat"],
        input_price_per_1m=0.3,
        output_price_per_1m=1.2,
        description="DeepSeek V4 Flash，低成本通用",
    ),
    "kimi-k3": ModelCatalogEntry(
        alias="kimi-k3",
        name="Kimi K3",
        provider_type="openai",
        default_model_id="kimi-k3",
        capabilities=["coding", "reasoning", "tool_use", "vision"],
        input_price_per_1m=3.0,
        output_price_per_1m=15.0,
        description="Moonshot Kimi K3 旗舰（2026-07-16 发布），1M 上下文；元数据来自发布报道，未逐项核实",
        context_window_tokens=1_048_576,
        max_output_tokens=131_072,
        context_window_source="unverified_press_2026-07",
    ),
    "kimi-k2.7-code": ModelCatalogEntry(
        alias="kimi-k2.7-code",
        name="Kimi K2.7 Code",
        provider_type="openai",
        default_model_id="kimi-k2.7-code",
        capabilities=["coding", "tool_use", "reasoning"],
        input_price_per_1m=1.0,
        output_price_per_1m=1.0,
        description="Kimi K2.7 编程模型，OpenAI 兼容接口",
    ),
    "kimi-k2.7": ModelCatalogEntry(
        alias="kimi-k2.7",
        name="Kimi K2.7",
        provider_type="openai",
        default_model_id="kimi-k2.7",
        capabilities=["coding", "reasoning", "tool_use"],
        input_price_per_1m=1.0,
        output_price_per_1m=1.0,
        description="Kimi K2.7 通用模型",
    ),
    "kimi-k2.5": ModelCatalogEntry(
        alias="kimi-k2.5",
        name="Kimi K2.5",
        provider_type="openai",
        default_model_id="kimi-k2.5",
        capabilities=["chat", "tool_use"],
        input_price_per_1m=1.0,
        output_price_per_1m=1.0,
        description="Kimi K2.5 对话模型",
    ),
    "glm-5": ModelCatalogEntry(
        alias="glm-5",
        name="GLM-5",
        provider_type="openai",
        default_model_id="glm-5",
        capabilities=["coding", "reasoning", "tool_use"],
        input_price_per_1m=1.0,
        output_price_per_1m=1.0,
        description="智谱 GLM-5 旗舰模型",
    ),
    "glm-4-flash": ModelCatalogEntry(
        alias="glm-4-flash",
        name="GLM-4 Flash",
        provider_type="openai",
        default_model_id="glm-4-flash",
        capabilities=["chat"],
        input_price_per_1m=0.1,
        output_price_per_1m=0.1,
        description="智谱 GLM-4 Flash，低成本对话",
    ),
    "minimax-m2.7": ModelCatalogEntry(
        alias="minimax-m2.7",
        name="MiniMax M2.7",
        provider_type="openai",
        default_model_id="MiniMax-M2.7",
        capabilities=["coding", "tool_use", "reasoning"],
        input_price_per_1m=1.0,
        output_price_per_1m=1.0,
        description="MiniMax M2.7，编程与 Agent",
    ),
    "qwen3-coder-plus": ModelCatalogEntry(
        alias="qwen3-coder-plus",
        name="Qwen3 Coder Plus",
        provider_type="openai",
        default_model_id="qwen3-coder-plus",
        capabilities=["coding", "tool_use", "reasoning"],
        input_price_per_1m=1.0,
        output_price_per_1m=1.0,
        description="阿里通义 Qwen3 Coder Plus",
    ),
    "qwen3-235b-a22b": ModelCatalogEntry(
        alias="qwen3-235b-a22b",
        name="Qwen3 235B A22B",
        provider_type="openai",
        default_model_id="qwen3-235b-a22b",
        capabilities=["coding", "reasoning"],
        input_price_per_1m=1.0,
        output_price_per_1m=1.0,
        description="阿里通义 Qwen3 235B MoE",
    ),
    "doubao-seed": ModelCatalogEntry(
        alias="doubao-seed",
        name="豆包 Seed 2.1 Pro",
        provider_type="openai",
        default_model_id="doubao-seed-2-1-pro-260628",
        capabilities=["coding", "reasoning"],
        input_price_per_1m=1.0,
        output_price_per_1m=1.0,
        description="字节豆包 Seed 2.1 Pro（火山方舟 OpenAI 兼容）",
    ),
    "gemini-3.1-pro": ModelCatalogEntry(
        alias="gemini-3.1-pro",
        name="Gemini 3.1 Pro",
        provider_type="openai",
        default_model_id="gemini-3.1-pro-preview",
        capabilities=["coding", "reasoning", "vision", "tool_use"],
        input_price_per_1m=2.0,
        output_price_per_1m=12.0,
        description="Google Gemini 3.1 Pro（OpenAI 兼容端点）",
    ),
    "gemini-3.5-flash": ModelCatalogEntry(
        alias="gemini-3.5-flash",
        name="Gemini 3.5 Flash",
        provider_type="openai",
        default_model_id="gemini-3.5-flash",
        capabilities=["coding", "reasoning", "tool_use"],
        input_price_per_1m=1.5,
        output_price_per_1m=9.0,
        description="Google Gemini 3.5 Flash，快速编程",
    ),
    "gemini-3-flash": ModelCatalogEntry(
        alias="gemini-3-flash",
        name="Gemini 3 Flash",
        provider_type="openai",
        default_model_id="gemini-3-flash-preview",
        capabilities=["chat", "tool_use"],
        input_price_per_1m=0.5,
        output_price_per_1m=3.0,
        description="Google Gemini 3 Flash，低成本",
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
        "supported_models": ["gpt-5", "gpt-4o", "gpt-4o-mini"],
    },
    "anthropic": {
        "name": "Anthropic",
        "type": "anthropic",
        "base_url": "https://api.anthropic.com",
        "timeout": 120,
        "rpm_limit": 60,
        "supported_models": [
            "claude-fable-5",
            "claude-opus-4-8",
            "claude-sonnet-5",
            "claude-haiku-4-5",
        ],
    },
    "kimi": {
        "name": "Kimi 转发",
        "type": "openai",
        "base_url": "https://api.moonshot.cn/v1",
        "timeout": 120,
        "rpm_limit": 60,
        "supported_models": ["kimi-k3", "kimi-k2.7-code", "kimi-k2.7", "kimi-k2.5", "kimi-for-coding"],
    },
    "deepseek": {
        "name": "DeepSeek",
        "type": "openai",
        "base_url": "https://api.deepseek.com/v1",
        "timeout": 120,
        "rpm_limit": 60,
        "supported_models": [
            "deepseek-v4-pro",
            "deepseek-v4-flash",
            "deepseek-chat",
            "deepseek-reasoner",
        ],
    },
    "zhipu_glm": {
        "name": "智谱 GLM",
        "type": "openai",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "timeout": 120,
        "rpm_limit": 60,
        "supported_models": ["glm-5", "glm-4-flash"],
    },
    "qwen": {
        "name": "阿里通义千问 (DashScope)",
        "type": "openai",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "timeout": 120,
        "rpm_limit": 60,
        "supported_models": ["qwen3-coder-plus", "qwen3-235b-a22b"],
    },
    "minimax": {
        "name": "MiniMax",
        "type": "openai",
        "base_url": "https://api.minimaxi.com/v1",
        "timeout": 120,
        "rpm_limit": 60,
        "supported_models": ["minimax-m2.7"],
    },
    "ark_openai": {
        "name": "火山方舟 (OpenAI 兼容)",
        "type": "openai",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "timeout": 120,
        "rpm_limit": 60,
        "supported_models": ["doubao-seed"],
    },
    "gemini": {
        "name": "Google Gemini (OpenAI 兼容)",
        "type": "openai",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "timeout": 120,
        "rpm_limit": 60,
        "supported_models": ["gemini-3.1-pro", "gemini-3.5-flash", "gemini-3-flash"],
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
