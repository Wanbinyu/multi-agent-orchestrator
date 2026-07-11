from src.ui.presets import register_preset

register_preset(
    "zhipu-glm",
    {
        "name": "智谱 GLM",
        "type": "openai",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "env_var": "GLM_API_KEY",
        "models": {
            "glm-5": {
                "model_id": "glm-5",
                "input_price_per_1m": 1.0,
                "output_price_per_1m": 1.0,
                "capabilities": ["coding", "reasoning", "tool_use"],
            },
            "glm-4-flash": {
                "model_id": "glm-4-flash",
                "input_price_per_1m": 0.1,
                "output_price_per_1m": 0.1,
                "capabilities": ["chat"],
            },
        },
    },
)
