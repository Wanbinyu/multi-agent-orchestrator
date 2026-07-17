from src.models.catalog import BUILTIN_MODELS
from src.ui.presets import register_preset

register_preset(
    "ark",
    {
        "name": "火山方舟 (OpenAI 兼容)",
        "type": "openai",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "env_var": "ARK_API_KEY",
        "models": {
            alias: BUILTIN_MODELS[alias].to_model_data()
            for alias in ("doubao-seed",)
        },
    },
)
