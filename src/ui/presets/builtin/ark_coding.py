from src.models.catalog import BUILTIN_MODELS
from src.ui.presets import register_preset

register_preset(
    "ark-coding",
    {
        "name": "火山方舟 Coding Plan",
        "type": "anthropic",
        "base_url": "https://ark.cn-beijing.volces.com/api/coding",
        "env_var": "ARK_CODING_API_KEY",
        "models": {
            alias: BUILTIN_MODELS[alias].to_model_data()
            for alias in (
                "glm-ark",
                "glm-chat",
            )
        },
    },
)
