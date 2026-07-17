from src.models.catalog import BUILTIN_MODELS
from src.ui.presets import register_preset

register_preset(
    "zhipu-glm",
    {
        "name": "智谱 GLM",
        "type": "openai",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "env_var": "GLM_API_KEY",
        "models": {
            alias: BUILTIN_MODELS[alias].to_model_data()
            for alias in (
                "glm-5",
                "glm-4-flash",
            )
        },
    },
)
