from src.models.catalog import BUILTIN_MODELS
from src.ui.presets import register_preset


register_preset(
    "anthropic",
    {
        "name": "Anthropic (Claude Official)",
        "type": "anthropic",
        "base_url": "https://api.anthropic.com",
        "env_var": "ANTHROPIC_API_KEY",
        "models": {
            alias: BUILTIN_MODELS[alias].to_model_data()
            for alias in (
                "claude-fable-5",
                "claude-opus-4-8",
                "claude-sonnet-5",
                "claude-haiku-4-5",
            )
        },
    },
)
