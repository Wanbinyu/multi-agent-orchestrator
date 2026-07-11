from src.ui.presets import register_preset

register_preset(
    "minimax",
    {
        "name": "MiniMax",
        "type": "openai",
        "base_url": "https://api.minimaxi.com/v1",
        "env_var": "MINIMAX_API_KEY",
        "models": {
            "minimax-m2.7": {
                "model_id": "MiniMax-M2.7",
                "input_price_per_1m": 1.0,
                "output_price_per_1m": 1.0,
                "capabilities": ["coding", "tool_use", "reasoning"],
            },
        },
    },
)
