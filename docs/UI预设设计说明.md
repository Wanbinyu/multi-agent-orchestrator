# UI Provider 预设设计说明

> 日期：2026-07-11  
> 目标：把 CCswitch 等来源的 Provider 配置做成可扩展、易维护的预设系统，方便后续不断加入新模型或用户自部署模型。

---

## 一、设计原则

1. **模块化**：每个 Provider 一个文件，新增时无需改动核心代码。
2. **运行时注册**：通过 `register_preset(key, preset)` 向全局注册表注册。
3. **用户可扩展**：支持从 `config/presets/*.json` 或 `*.yaml` 加载自定义预设。
4. **与后端兼容**：所有预设的 `type` 必须是当前 Gateway 已支持的 `anthropic` 或 `openai`。
5. **不收费**：预设只是连接模板；实际调用哪家 API，才需要给那家付费。

---

## 二、目录结构

```text
src/ui/presets/
├── __init__.py          # 注册中心、公共函数、加载用户自定义预设
└── builtin/             # 内置常用 Provider
    ├── __init__.py
    ├── anthropic.py
    ├── openai.py
    ├── deepseek.py
    ├── ark.py
    ├── ark_coding.py
    ├── zhipu_glm.py
    ├── kimi.py
    ├── minimax.py
    ├── stepfun.py
    ├── qwen.py
    ├── baidu_qianfan.py
    ├── siliconflow.py
    ├── openrouter.py
    ├── azure_openai.py
    ├── custom_anthropic.py
    └── custom_openai.py
```

---

## 三、如何新增一个内置 Provider

在 `src/ui/presets/builtin/` 下新建 `.py` 文件，例如 `example.py`：

```python
from src.ui.presets import register_preset

register_preset(
    "example",
    {
        "name": "Example Provider",
        "type": "openai",
        "base_url": "https://api.example.com/v1",
        "env_var": "EXAMPLE_API_KEY",
        "models": {
            "example-coder": {
                "model_id": "example-coder-latest",
                "input_price_per_1m": 1.0,
                "output_price_per_1m": 1.0,
                "capabilities": ["coding", "tool_use"],
            },
        },
    },
)
```

然后在 `src/ui/presets/__init__.py` 的底部导入该模块：

```python
from src.ui.presets.builtin import example  # noqa: F401
```

重启 UI 后即可在预设下拉框中看到。

---

## 四、用户自定义预设

用户无需改代码，只需在 `config/presets/` 目录下放置 JSON 或 YAML 文件。

示例 `config/presets/my-local-model.json`：

```json
{
  "key": "my-local",
  "name": "我的本地模型",
  "type": "openai",
  "base_url": "http://localhost:8000/v1",
  "env_var": "MY_LOCAL_API_KEY",
  "models": {
    "local-coder": {
      "model_id": "qwen2.5-coder",
      "input_price_per_1m": 0.0,
      "output_price_per_1m": 0.0,
      "capabilities": ["coding"]
    }
  }
}
```

启动 UI 时会自动加载。

---

## 五、当前内置常用 Provider 列表

| key | 名称 | 协议 | Base URL 示例 |
|---|---|---|---|
| `anthropic` | Anthropic (Claude Official) | anthropic | `https://api.anthropic.com` |
| `openai` | OpenAI | openai | `https://api.openai.com/v1` |
| `deepseek` | DeepSeek | openai | `https://api.deepseek.com/v1` |
| `ark` | 火山方舟 (OpenAI 兼容) | openai | `https://ark.cn-beijing.volces.com/api/v3` |
| `ark-coding` | 火山方舟 Coding Plan | anthropic | `https://ark.cn-beijing.volces.com/api/coding` |
| `zhipu-glm` | 智谱 GLM | openai | `https://open.bigmodel.cn/api/paas/v4` |
| `kimi` | Kimi (Moonshot) | openai | `https://api.moonshot.cn/v1` |
| `minimax` | MiniMax | openai | `https://api.minimaxi.com/v1` |
| `stepfun` | 阶跃星辰 StepFun | openai | `https://api.stepfun.com/v1` |
| `qwen` | 阿里通义千问 (DashScope) | openai | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| `baidu-qianfan` | 百度千帆 (Qianfan) | openai | `https://qianfan.baidubce.com/v2` |
| `siliconflow` | SiliconFlow | openai | `https://api.siliconflow.cn/v1` |
| `openrouter` | OpenRouter | openai | `https://openrouter.ai/api/v1` |
| `azure-openai` | Azure OpenAI（需替换资源名） | openai | `https://YOUR_RESOURCE_NAME.openai.azure.com/openai` |
| `custom-anthropic` | 自定义 Anthropic 兼容服务 | anthropic | 用户填写 |
| `custom-openai` | 自定义 OpenAI 兼容服务 | openai | 用户填写 |

---

## 六、注意事项

- 预设只包含连接参数，**不包含 API Key**；Key 由用户在 UI 中输入后写入 `.env`。
- 第三方转发/聚合服务（如 OpenRouter、SiliconFlow）的稳定性由各服务商决定，使用时请自行评估。
- Azure OpenAI 需要把 Base URL 中的 `YOUR_RESOURCE_NAME` 替换为真实资源名。
- 若未来 Gateway 支持 Gemini Native 或 AWS Bedrock，可再新增对应预设文件。

---

## 七、测试

新增或修改预设后，运行：

```powershell
python -m pytest tests/test_ui.py -v
```

全量测试：

```powershell
python -m pytest -q
```

当前全量测试：134 passed。
