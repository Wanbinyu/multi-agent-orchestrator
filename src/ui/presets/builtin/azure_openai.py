from src.ui.presets import register_preset

register_preset(
    "azure-openai",
    {
        "name": "Azure OpenAI（需替换 YOUR_RESOURCE_NAME）",
        "type": "openai",
        "base_url": "https://YOUR_RESOURCE_NAME.openai.azure.com/openai",
        "env_var": "AZURE_OPENAI_API_KEY",
        "note": "Azure uses deployment name, not a universal upstream model_id; replace the resource and deployment placeholders.",
        "models": {
            "azure-deployment": {
                "model_id": "YOUR_DEPLOYMENT_NAME",
                "input_price_per_1m": 5.0,
                "output_price_per_1m": 15.0,
                "capabilities": ["coding", "reasoning", "vision", "tool_use"],
            },
        },
    },
)
