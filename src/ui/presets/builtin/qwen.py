from src.ui.presets import register_preset

register_preset(
    "qwen",
    {
        "name": "阿里通义千问 (DashScope)",
        "type": "openai",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "env_var": "DASHSCOPE_API_KEY",
        "models": {
            "qwen3-coder-plus": {
                "model_id": "qwen3-coder-plus",
                "input_price_per_1m": 1.0,
                "output_price_per_1m": 1.0,
                "capabilities": ["coding", "tool_use", "reasoning"],
            },
            "qwen3-235b-a22b": {
                "model_id": "qwen3-235b-a22b",
                "input_price_per_1m": 1.0,
                "output_price_per_1m": 1.0,
                "capabilities": ["coding", "reasoning"],
            },
        },
    },
)
