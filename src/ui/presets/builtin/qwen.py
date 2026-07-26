from src.models.catalog import BUILTIN_MODELS
from src.ui.presets import register_preset

register_preset(
    "qwen",
    {
        "name": "阿里通义千问 (DashScope)",
        "type": "openai",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "env_var": "DASHSCOPE_API_KEY",
        "models": {
            alias: BUILTIN_MODELS[alias].to_model_data()
            for alias in (
                "qwen3.8-max-preview",
                "qwen3.7-max",
                "qwen3.7-plus",
                "qwen3.7-flash",
            )
        },
    },
)
