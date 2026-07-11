from src.ui.presets import register_preset

register_preset(
    "siliconflow",
    {
        "name": "SiliconFlow",
        "type": "openai",
        "base_url": "https://api.siliconflow.cn/v1",
        "env_var": "SILICONFLOW_API_KEY",
        "models": {
            "qwen3-235b-a22b": {
                "model_id": "Qwen/Qwen3-235B-A22B",
                "input_price_per_1m": 1.0,
                "output_price_per_1m": 1.0,
                "capabilities": ["coding", "reasoning"],
            },
            "glm-5": {
                "model_id": "zai-org/glm-5.1",
                "input_price_per_1m": 1.0,
                "output_price_per_1m": 1.0,
                "capabilities": ["coding", "reasoning"],
            },
        },
    },
)
