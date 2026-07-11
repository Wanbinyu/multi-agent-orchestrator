from src.ui.presets import register_preset

register_preset(
    "ark-coding",
    {
        "name": "火山方舟 Coding Plan",
        "type": "anthropic",
        "base_url": "https://ark.cn-beijing.volces.com/api/coding",
        "env_var": "ARK_CODING_API_KEY",
        "models": {
            "glm-ark": {
                "model_id": "ark-code-latest",
                "input_price_per_1m": 1.0,
                "output_price_per_1m": 1.0,
                "capabilities": ["coding", "tool_use", "reasoning"],
            },
            "glm-chat": {
                "model_id": "ark-chat-latest",
                "input_price_per_1m": 1.0,
                "output_price_per_1m": 1.0,
                "capabilities": ["chat", "tool_use"],
            },
        },
    },
)
