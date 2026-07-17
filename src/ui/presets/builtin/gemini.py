from src.models.catalog import BUILTIN_MODELS
from src.ui.presets import register_preset

register_preset(
    "gemini",
    {
        "name": "Google Gemini (OpenAI 兼容)",
        "type": "openai",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "env_var": "GEMINI_API_KEY",
        "models": {
            alias: BUILTIN_MODELS[alias].to_model_data()
            for alias in (
                "gemini-3.1-pro",
                "gemini-3.5-flash",
                "gemini-3-flash",
            )
        },
    },
)
