from src.models.catalog import BUILTIN_MODELS
from src.ui.presets import register_preset

register_preset(
    "minimax",
    {
        "name": "MiniMax",
        "type": "openai",
        "base_url": "https://api.minimaxi.com/v1",
        "env_var": "MINIMAX_API_KEY",
        "models": {
            alias: BUILTIN_MODELS[alias].to_model_data()
            for alias in ("minimax-m2.7",)
        },
    },
)
