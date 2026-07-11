from src.ui.presets import register_preset

register_preset(
    "custom-anthropic",
    {
        "name": "自定义 Anthropic 兼容服务",
        "type": "anthropic",
        "base_url": "",
        "env_var": "CUSTOM_ANTHROPIC_API_KEY",
        "models": {},
    },
)
