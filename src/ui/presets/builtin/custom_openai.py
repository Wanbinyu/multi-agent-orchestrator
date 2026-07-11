from src.ui.presets import register_preset

register_preset(
    "custom-openai",
    {
        "name": "自定义 OpenAI 兼容服务",
        "type": "openai",
        "base_url": "",
        "env_var": "CUSTOM_OPENAI_API_KEY",
        "models": {},
        "note": "适合本地模型、用户自部署模型或其他 OpenAI 兼容服务",
    },
)
