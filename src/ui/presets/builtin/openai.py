from src.models.catalog import BUILTIN_MODELS
from src.ui.presets import register_preset

register_preset(
    "openai",
    {
        "name": "OpenAI",
        "type": "openai",
        "base_url": "https://api.openai.com/v1",
        "env_var": "OPENAI_API_KEY",
        "models": {
            alias: BUILTIN_MODELS[alias].to_model_data()
            for alias in (
                "gpt-5",
                "gpt-4o",
                "gpt-4o-mini",
            )
        },
    },
)
