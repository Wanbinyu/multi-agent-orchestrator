from src.models.catalog import BUILTIN_MODELS
from src.ui.presets import register_preset

register_preset(
    "kimi",
    {
        "name": "Kimi (Moonshot)",
        "type": "openai",
        "base_url": "https://api.moonshot.cn/v1",
        "env_var": "KIMI_API_KEY",
        "models": {
            alias: BUILTIN_MODELS[alias].to_model_data()
            for alias in (
                "kimi-k3",
                "kimi-k2.7-code",
                "kimi-k2.7",
                "kimi-k2.5",
            )
        },
    },
)
