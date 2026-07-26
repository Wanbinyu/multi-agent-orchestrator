from src.models.catalog import BUILTIN_MODELS
from src.ui.presets import register_preset

register_preset(
    "kimi-coding",
    {
        "name": "Kimi Coding Plan",
        "type": "openai",
        "base_url": "https://api.kimi.com/coding/v1",
        "env_var": "KIMI_CODING_API_KEY",
        "models": {
            alias: BUILTIN_MODELS[alias].to_model_data()
            for alias in (
                "k3",
                "k3-256k",
                "kimi-for-coding",
                "kimi-for-coding-highspeed",
            )
        },
    },
)
