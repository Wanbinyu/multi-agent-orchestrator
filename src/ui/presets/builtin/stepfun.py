from src.ui.presets import register_preset

register_preset(
    "stepfun",
    {
        "name": "阶跃星辰 StepFun",
        "type": "openai",
        "base_url": "https://api.stepfun.com/v1",
        "env_var": "STEPFUN_API_KEY",
        "models": {
            "step-3.7-flash": {
                "model_id": "step-3.7-flash",
                "input_price_per_1m": 1.0,
                "output_price_per_1m": 1.0,
                "capabilities": ["coding", "reasoning"],
            },
        },
    },
)
