from src.ui.presets import register_preset

register_preset(
    "openai",
    {
        "name": "OpenAI",
        "type": "openai",
        "base_url": "https://api.openai.com/v1",
        "env_var": "OPENAI_API_KEY",
        "models": {
            "gpt-5": {
                "model_id": "gpt-5",
                "input_price_per_1m": 5.0,
                "output_price_per_1m": 15.0,
                "capabilities": ["coding", "reasoning", "vision", "tool_use"],
            },
            "gpt-4o": {
                "model_id": "gpt-4o",
                "input_price_per_1m": 5.0,
                "output_price_per_1m": 15.0,
                "capabilities": ["coding", "reasoning", "vision", "tool_use"],
            },
            "gpt-4o-mini": {
                "model_id": "gpt-4o-mini",
                "input_price_per_1m": 0.15,
                "output_price_per_1m": 0.6,
                "capabilities": ["chat", "vision"],
            },
        },
    },
)
