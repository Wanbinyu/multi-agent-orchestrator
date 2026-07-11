from src.ui.presets import register_preset

register_preset(
    "ark",
    {
        "name": "火山方舟 (OpenAI 兼容)",
        "type": "openai",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "env_var": "ARK_API_KEY",
        "models": {
            "doubao-seed": {
                "model_id": "doubao-seed-2-1-pro-260628",
                "input_price_per_1m": 1.0,
                "output_price_per_1m": 1.0,
                "capabilities": ["coding", "reasoning"],
            },
        },
    },
)
