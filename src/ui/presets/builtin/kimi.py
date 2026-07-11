from src.ui.presets import register_preset

register_preset(
    "kimi",
    {
        "name": "Kimi (Moonshot)",
        "type": "openai",
        "base_url": "https://api.moonshot.cn/v1",
        "env_var": "KIMI_API_KEY",
        "models": {
            "kimi-k2.7-code": {
                "model_id": "kimi-k2.7-code",
                "input_price_per_1m": 1.0,
                "output_price_per_1m": 1.0,
                "capabilities": ["coding", "tool_use", "reasoning"],
            },
            "kimi-k2.7": {
                "model_id": "kimi-k2.7",
                "input_price_per_1m": 1.0,
                "output_price_per_1m": 1.0,
                "capabilities": ["coding", "reasoning", "tool_use"],
            },
            "kimi-k2.5": {
                "model_id": "kimi-k2.5",
                "input_price_per_1m": 1.0,
                "output_price_per_1m": 1.0,
                "capabilities": ["chat", "tool_use"],
            },
        },
    },
)
