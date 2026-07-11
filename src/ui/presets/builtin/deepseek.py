from src.ui.presets import register_preset

register_preset(
    "deepseek",
    {
        "name": "DeepSeek",
        "type": "openai",
        "base_url": "https://api.deepseek.com/v1",
        "env_var": "DEEPSEEK_API_KEY",
        "models": {
            "deepseek-v4-pro": {
                "model_id": "deepseek-v4-pro",
                "input_price_per_1m": 1.0,
                "output_price_per_1m": 4.0,
                "capabilities": ["coding", "reasoning"],
            },
            "deepseek-v4-flash": {
                "model_id": "deepseek-v4-flash",
                "input_price_per_1m": 0.3,
                "output_price_per_1m": 1.2,
                "capabilities": ["coding", "chat"],
            },
        },
    },
)
