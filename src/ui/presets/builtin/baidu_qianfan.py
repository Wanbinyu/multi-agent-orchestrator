from src.ui.presets import register_preset

register_preset(
    "baidu-qianfan",
    {
        "name": "百度千帆 (Qianfan)",
        "type": "openai",
        "base_url": "https://qianfan.baidubce.com/v2",
        "env_var": "QIANFAN_API_KEY",
        "models": {
            "qianfan-code-latest": {
                "model_id": "qianfan-code-latest",
                "input_price_per_1m": 1.0,
                "output_price_per_1m": 1.0,
                "capabilities": ["coding", "tool_use"],
            },
        },
    },
)
