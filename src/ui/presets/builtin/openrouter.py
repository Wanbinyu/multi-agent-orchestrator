from src.ui.presets import register_preset

register_preset(
    "openrouter",
    {
        "name": "OpenRouter (按其模型目录核对)",
        "type": "openai",
        "base_url": "https://openrouter.ai/api/v1",
        "env_var": "OPENROUTER_API_KEY",
        "note": "OpenRouter 的模型可用性、名称和价格随其目录及账号变化；MAO 不将此聚合入口视为官方直连验证。",
        "models": {
            "claude-opus-5": {
                "model_id": "anthropic/claude-opus-5",
                "input_price_per_1m": 3.0,
                "output_price_per_1m": 15.0,
                "capabilities": ["coding", "reasoning", "vision", "tool_use"],
                "metadata_source": "unverified_openrouter_catalog",
            },
            "gpt-5.6-terra": {
                "model_id": "openai/gpt-5.6-terra",
                "input_price_per_1m": 2.5,
                "output_price_per_1m": 15.0,
                "capabilities": ["coding", "reasoning", "vision", "tool_use"],
                "metadata_source": "unverified_openrouter_catalog",
            },
        },
    },
)
