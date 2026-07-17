from src.models.catalog import BUILTIN_MODELS
from src.ui.presets import register_preset

register_preset(
    "deepseek",
    {
        "name": "DeepSeek",
        "type": "openai",
        "base_url": "https://api.deepseek.com/v1",
        "env_var": "DEEPSEEK_API_KEY",
        "models": {
            alias: BUILTIN_MODELS[alias].to_model_data()
            for alias in (
                "deepseek-v4-pro",
                "deepseek-v4-flash",
            )
        },
    },
)
