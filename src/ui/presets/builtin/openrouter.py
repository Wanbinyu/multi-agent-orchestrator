from src.ui.presets import register_preset

register_preset(
    "openrouter",
    {
        "name": "OpenRouter",
        "type": "openai",
        "base_url": "https://openrouter.ai/api/v1",
        "env_var": "OPENROUTER_API_KEY",
        "models": {
            "claude-sonnet-5": {
                "model_id": "anthropic/claude-sonnet-5",
                "input_price_per_1m": 3.0,
                "output_price_per_1m": 15.0,
                "capabilities": ["coding", "reasoning", "vision", "tool_use"],
            },
            "gpt-4o": {
                "model_id": "openai/gpt-4o",
                "input_price_per_1m": 5.0,
                "output_price_per_1m": 15.0,
                "capabilities": ["coding", "reasoning", "vision", "tool_use"],
            },
        },
    },
)
