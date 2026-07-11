from src.ui.presets import register_preset

register_preset(
    "anthropic",
    {
        "name": "Anthropic (Claude Official)",
        "type": "anthropic",
        "base_url": "https://api.anthropic.com",
        "env_var": "ANTHROPIC_API_KEY",
        "models": {
            "claude-fable-5": {
                "model_id": "claude-fable-5-20251001",
                "input_price_per_1m": 15.0,
                "output_price_per_1m": 75.0,
                "capabilities": ["coding", "reasoning", "vision", "tool_use"],
            },
            "claude-sonnet-5": {
                "model_id": "claude-sonnet-5-20251001",
                "input_price_per_1m": 3.0,
                "output_price_per_1m": 15.0,
                "capabilities": ["coding", "reasoning", "vision", "tool_use"],
            },
            "claude-haiku-4-5": {
                "model_id": "claude-haiku-4-5-20251001",
                "input_price_per_1m": 0.25,
                "output_price_per_1m": 1.25,
                "capabilities": ["chat", "vision"],
            },
        },
    },
)
