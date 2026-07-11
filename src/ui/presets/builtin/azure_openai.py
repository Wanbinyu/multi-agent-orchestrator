from src.ui.presets import register_preset

register_preset(
    "azure-openai",
    {
        "name": "Azure OpenAI（需替换 YOUR_RESOURCE_NAME）",
        "type": "openai",
        "base_url": "https://YOUR_RESOURCE_NAME.openai.azure.com/openai",
        "env_var": "AZURE_OPENAI_API_KEY",
        "models": {
            "azure-gpt-4o": {
                "model_id": "gpt-4o",
                "input_price_per_1m": 5.0,
                "output_price_per_1m": 15.0,
                "capabilities": ["coding", "reasoning", "vision", "tool_use"],
            },
        },
    },
)
