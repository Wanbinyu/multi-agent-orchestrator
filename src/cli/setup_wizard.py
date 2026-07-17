"""交互式配置向导

运行：python run.py setup
"""
from __future__ import annotations

import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import questionary
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule

from src.cli.provider_presets import (
    PROVIDER_PRESETS,
    build_providers_yaml,
    get_default_models_for_provider,
    list_provider_choices,
    validate_custom_provider,
)

console = Console()

# ========== 场景预设 ==========

SCENARIOS: dict[str, dict[str, Any]] = {
    "software_dev": {
        "name": "软件开发",
        "description": "前后端分离的 Web / 应用开发",
        "orchestrator_model": "glm-ark",
        "workers": [
            {
                "key": "frontend",
                "name": "前端开发",
                "default_model": "claude-sonnet-5",
                "system_prompt": "你是资深前端工程师，擅长 React + TypeScript + Tailwind CSS。请根据任务要求输出可直接运行的代码，附带简短说明。",
                "tools": ["write_file", "read_file", "run_command"],
                "allowed_commands": ["npm ", "node ", "npx "],
            },
            {
                "key": "backend",
                "name": "后端开发",
                "default_model": "glm-ark",
                "system_prompt": "你是资深后端工程师，擅长 Python + FastAPI + SQLAlchemy。请根据任务要求输出可直接运行的代码，附带简短说明。",
                "tools": ["write_file", "read_file", "run_command"],
                "allowed_commands": ["pytest", "python -m pytest", "python "],
            },
            {
                "key": "test",
                "name": "测试工程师",
                "default_model": "claude-haiku-4-5",
                "system_prompt": "你是测试工程师。请为提供的代码编写单元测试，使用 pytest。只输出测试代码和运行说明。",
                "tools": ["write_file", "read_file", "run_command"],
                "allowed_commands": ["pytest", "python -m pytest", "python "],
            },
            {
                "key": "doc",
                "name": "文档工程师",
                "default_model": "glm-4-flash",
                "system_prompt": "你是技术文档工程师。请根据项目内容生成清晰的中文 README 文档。",
                "tools": ["write_file", "read_file"],
            },
        ],
    },
    "novel_writing": {
        "name": "小说/内容创作",
        "description": "长篇小说、短篇故事、剧本等内容创作",
        "orchestrator_model": "glm-ark",
        "workers": [
            {
                "key": "plot_designer",
                "name": "大纲设计",
                "default_model": "glm-ark",
                "system_prompt": "你是资深小说编辑，擅长故事结构与世界观设计。请根据需求输出清晰的大纲、人物设定和章节规划。",
            },
            {
                "key": "writer",
                "name": "正文创作",
                "default_model": "glm-ark",
                "system_prompt": "你是专业小说作者。请根据大纲和角色设定，输出高质量、有画面感、符合人设的正文内容。",
            },
            {
                "key": "editor",
                "name": "润色修改",
                "default_model": "claude-haiku-4-5",
                "system_prompt": "你是文字编辑。请对提供的段落进行润色，修正语病、提升流畅度，保持原有风格。",
            },
            {
                "key": "continuity_checker",
                "name": "一致性检查",
                "default_model": "glm-4-flash",
                "system_prompt": "你是设定审查员。请检查故事前后设定是否一致，指出矛盾点并给出修改建议。",
            },
        ],
    },
    "game_modding": {
        "name": "游戏二次开发",
        "description": "Unity / 手游 / 私服等游戏的资源、配置、脚本修改",
        "orchestrator_model": "glm-ark",
        "workers": [
            {
                "key": "asset_analyzer",
                "name": "资源分析",
                "default_model": "glm-ark",
                "system_prompt": "你是游戏资源分析专家，熟悉 Unity AssetBundle、手游资源结构。请分析提供的资源文件结构并给出修改建议。",
            },
            {
                "key": "code_modder",
                "name": "代码修改",
                "default_model": "glm-ark",
                "system_prompt": "你是游戏逆向/修改工程师，熟悉 C#、Lua、Python 反编译与补丁。请根据需求输出可执行的修改代码。",
            },
            {
                "key": "config_designer",
                "name": "配置设计",
                "default_model": "claude-haiku-4-5",
                "system_prompt": "你是游戏数值/配置设计师。请根据需求设计合理的配置文件、数值表或掉落表。",
            },
            {
                "key": "tester",
                "name": "功能验证",
                "default_model": "glm-4-flash",
                "system_prompt": "你是游戏测试员。请根据修改内容列出验证步骤、可能的风险点和回滚方案。",
            },
        ],
    },
    "software_testing": {
        "name": "软件测试",
        "description": "为已有项目设计测试用例、编写自动化测试脚本",
        "orchestrator_model": "glm-ark",
        "workers": [
            {
                "key": "test_designer",
                "name": "测试设计",
                "default_model": "glm-ark",
                "system_prompt": "你是测试架构师。请根据需求/代码设计测试策略、测试用例和覆盖范围。",
            },
            {
                "key": "test_coder",
                "name": "测试开发",
                "default_model": "claude-sonnet-5",
                "system_prompt": "你是测试开发工程师，擅长 pytest、Selenium、Playwright。请输出可直接运行的自动化测试代码。",
            },
            {
                "key": "bug_reporter",
                "name": "缺陷报告",
                "default_model": "glm-4-flash",
                "system_prompt": "你是 QA 工程师。请根据测试结果整理缺陷报告，包含复现步骤、预期结果、实际结果。",
            },
        ],
    },
    "custom": {
        "name": "自定义",
        "description": "自己定义主工程师和子工程师",
        "orchestrator_model": "glm-ark",
        "workers": [],
    },
}

# 所有可用模型（从 providers.yaml 读取，这里先放默认值用于提示）
DEFAULT_MODELS = [
    "claude-fable-5",
    "claude-sonnet-5",
    "claude-haiku-4-5",
    "gpt-5",
    "gpt-4o-mini",
    "glm-5",
    "glm-4-flash",
    "glm-ark",
    "deepseek-v4-pro",
    "deepseek-v4-flash",
    "kimi-k3",
    "kimi-k2.7-code",
    "qwen3-coder-plus",
    "gemini-3.1-pro",
]


def load_existing_config(config_dir: str) -> tuple[dict, dict]:
    """加载已有配置，不存在则返回空"""
    providers_path = Path(config_dir) / "providers.yaml"
    workers_path = Path(config_dir) / "workers.yaml"

    providers_data = {}
    workers_data = {}

    if providers_path.exists():
        with open(providers_path, "r", encoding="utf-8") as f:
            providers_data = yaml.safe_load(f) or {}

    if workers_path.exists():
        with open(workers_path, "r", encoding="utf-8") as f:
            workers_data = yaml.safe_load(f) or {}

    return providers_data, workers_data


def backup_config(config_dir: str):
    """备份现有配置文件"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    for filename in ["providers.yaml", "workers.yaml"]:
        src = Path(config_dir) / filename
        if src.exists():
            dst = Path(config_dir) / f"{filename}.{timestamp}.bak"
            shutil.copy2(src, dst)
            console.print(f"[yellow]已备份 {filename} → {dst.name}[/yellow]")


def get_available_models(config_dir: str) -> list[str]:
    """从 providers.yaml 读取可用模型名"""
    providers_path = Path(config_dir) / "providers.yaml"
    if not providers_path.exists():
        return DEFAULT_MODELS

    with open(providers_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    models = list(data.get("models", {}).keys())
    return models if models else DEFAULT_MODELS


def ask_scenario() -> str:
    """选择使用场景"""
    choices = [
        questionary.Choice(title=f"{v['name']} — {v['description']}", value=k)
        for k, v in SCENARIOS.items()
    ]

    return questionary.select(
        "你想用这个工具做什么？",
        choices=choices,
        instruction="按 ↑↓ 选择，Enter 确认",
    ).ask()


def ask_orchestrator_model(available_models: list[str], default: str) -> str:
    """配置总指挥模型"""
    console.print(Rule("[bold cyan]主工程师（总指挥）配置[/bold cyan]"))
    console.print(
        "总指挥负责理解你的需求、拆分任务、验收结果。\n"
        "建议选你手头上[bold]最强、最稳定[/bold]的模型。\n"
    )

    model = questionary.select(
        "选择总指挥模型：",
        choices=available_models,
        default=default if default in available_models else available_models[0],
    ).ask()

    return model


def ask_workers(available_models: list[str], preset_workers: list[dict]) -> list[dict]:
    """配置子工程师"""
    console.print(Rule("[bold cyan]子工程师（Worker）配置[/bold cyan]"))
    console.print(
        "子工程师负责具体执行任务。不同场景下可以配置不同角色。\n"
        "你可以使用推荐配置，也可以自己增删改。\n"
    )

    use_preset = questionary.confirm(
        "是否使用推荐的子工程师配置？",
        default=True,
    ).ask()

    workers = []
    if use_preset:
        workers = [dict(w) for w in preset_workers]
    else:
        # 从空开始，让用户自己添加
        pass

    # 允许用户修改每个 Worker
    if workers:
        console.print("\n[bold]推荐的子工程师：[/bold]")
        for i, w in enumerate(workers, 1):
            console.print(f"  {i}. {w['name']} ({w['key']}) → {w['default_model']}")

        modify = questionary.confirm("是否需要修改某个子工程师？", default=False).ask()
        if modify:
            workers = modify_workers(workers, available_models)

    # 允许添加自定义 Worker
    while questionary.confirm("是否添加新的子工程师？", default=False).ask():
        new_worker = create_worker(available_models)
        if new_worker:
            workers.append(new_worker)

    return workers


def modify_workers(workers: list[dict], available_models: list[str]) -> list[dict]:
    """修改现有 Worker 配置"""
    while True:
        choices = [
            questionary.Choice(title=f"{w['name']} ({w['key']})", value=i)
            for i, w in enumerate(workers)
        ]
        choices.append(questionary.Choice(title="完成修改", value=-1))

        idx = questionary.select("选择要修改的子工程师：", choices=choices).ask()
        if idx == -1:
            break

        w = workers[idx]
        w["name"] = questionary.text("名称：", default=w["name"]).ask()
        w["default_model"] = questionary.select(
            "默认模型：", choices=available_models, default=w["default_model"]
        ).ask()
        w["system_prompt"] = questionary.text("系统提示词（如需换行可写 \\n）：", default=w["system_prompt"]).ask()

    return workers


def create_worker(available_models: list[str]) -> dict | None:
    """创建新的 Worker"""
    key = questionary.text("子工程师标识（英文小写，如 data_analyst）：").ask()
    if not key:
        return None

    name = questionary.text("显示名称（如 数据分析师）：").ask()
    model = questionary.select("默认模型：", choices=available_models).ask()
    prompt = questionary.text("系统提示词（如需换行可写 \\n）：").ask()

    return {
        "key": key.strip().lower().replace(" ", "_"),
        "name": name,
        "default_model": model,
        "system_prompt": prompt,
        "tools": ["write_file"],
    }


def ask_api_keys(providers_data: dict, used_providers: set[str]) -> dict[str, str]:
    """询问需要的 API key"""
    console.print(Rule("[bold cyan]API Key 配置[/bold cyan]"))
    console.print("下面只询问你会用到的 Provider。Key 会保存到 .env 文件。\n")

    provider_configs = providers_data.get("providers", {})
    keys_to_ask = {}

    for provider_name in sorted(used_providers):
        cfg = provider_configs.get(provider_name, {})
        env_var = f"{provider_name.upper()}_API_KEY"
        # 从现有 .env 读取
        existing = os.environ.get(env_var, "")

        key = questionary.password(
            f"请输入 {cfg.get('name', provider_name)} 的 API Key（{env_var}）：",
            default=existing,
        ).ask()

        if key:
            keys_to_ask[env_var] = key

    return keys_to_ask


def collect_used_providers(orchestrator_model: str, workers: list[dict], config_dir: str) -> set[str]:
    """收集实际会用到的 provider"""
    providers_path = Path(config_dir) / "providers.yaml"
    with open(providers_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    models = data.get("models", {})
    used = set()

    for model_name in [orchestrator_model] + [w["default_model"] for w in workers]:
        cfg = models.get(model_name)
        if cfg:
            used.add(cfg["provider"])

    return used


def save_env(keys: dict[str, str], project_root: str):
    """保存 API key 到 .env"""
    env_path = Path(project_root) / ".env"

    existing_lines = []
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            existing_lines = f.readlines()

    # 解析已有内容
    existing_keys = {}
    new_lines = []
    for line in existing_lines:
        stripped = line.strip()
        if "=" in stripped and not stripped.startswith("#"):
            k, v = stripped.split("=", 1)
            existing_keys[k] = line
        else:
            new_lines.append(line)

    # 合并
    for k, v in keys.items():
        existing_keys[k] = f"{k}={v}\n"

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)
        f.write("\n# Auto-generated by setup wizard\n")
        for line in existing_keys.values():
            f.write(line)

    console.print(f"[green]API Key 已保存到 {env_path}[/green]")


def build_workers_yaml(orchestrator_model: str, workers: list[dict], reviewer_model: str | None = None) -> dict:
    """生成 workers.yaml 内容"""
    reviewer_model = reviewer_model or orchestrator_model
    worker_lines = [f"    - {w['key']}: {w['name']}，默认模型 {w['default_model']}" for w in workers]
    worker_list_text = "\n".join(worker_lines)

    orchestrator_prompt = f"""你是项目总工程师。用户会给出一个需求。
你必须：
1. 分析需求并拆成可并行子任务；
2. 为每个子任务指定：类型、输入、输出格式、验收标准；
3. 从 available_workers 中选出最合适的执行模型；
4. 任务必须可独立执行，上下文要完整。

可用 Worker 列表：
{worker_list_text}

输出必须是严格 JSON，格式如下：
{{
  "summary": "任务总览",
  "tasks": [
    {{
      "id": "t1",
      "type": "{workers[0]['key'] if workers else 'worker'}",
      "title": "任务标题",
      "input": "完整任务描述",
      "output_format": "输出格式要求",
      "acceptance": "验收标准",
      "assigned_model": "模型名"
    }}
  ]
}}"""

    reviewer_prompt = """你是审查工程师。你会收到多个子任务的执行结果。
请检查：
1. 各模块结果是否一致；
2. 是否满足原始需求；
3. 是否存在明显错误。
输出格式：{"passed": true/false, "issues": ["..."], "final_output": "整合后的最终内容"}"""

    available_workers = {}
    for w in workers:
        worker_cfg = {
            "name": w["name"],
            "default_model": w["default_model"],
            "system_prompt": w["system_prompt"],
            "tools": w.get("tools", ["write_file"]),
        }
        if "allowed_commands" in w:
            worker_cfg["allowed_commands"] = w["allowed_commands"]
        available_workers[w["key"]] = worker_cfg

    return {
        "orchestrator": {
            "model": orchestrator_model,
            "system_prompt": orchestrator_prompt,
        },
        "reviewer": {
            "model": reviewer_model,
            "system_prompt": reviewer_prompt,
        },
        "available_workers": available_workers,
    }


def save_yaml(data: dict, path: Path):
    """保存 YAML"""
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)


def ask_providers() -> tuple[dict, dict[str, str]]:
    """引导用户配置 Provider，返回 providers.yaml 内容和环境变量"""
    console.print(Rule("[bold cyan]Provider 配置[/bold cyan]"))
    console.print(
        "请选择你要接入的模型服务。每个服务需要填写 API Key。\n"
        "如果你是首次使用，建议至少选择一个总指挥会用到的服务。\n"
    )

    choices = list_provider_choices()
    selected_names = questionary.checkbox(
        "选择要接入的 Provider（空格选择，Enter 确认）：",
        choices=[questionary.Choice(title=name, value=key) for name, key in choices],
    ).ask()

    if not selected_names:
        console.print("[red]至少需要选择一个 Provider[/red]")
        return {}, {}

    selected: list[tuple[str, str, str | None, dict | None]] = []
    for key in selected_names:
        preset = PROVIDER_PRESETS[key]
        console.print(f"\n[bold]▸ {preset['name']}[/bold]")

        # API Key
        env_var = preset["env_var"]
        api_key = questionary.password(
            f"请输入 {preset['name']} 的 API Key（环境变量 {env_var}）：",
        ).ask()
        if not api_key:
            console.print(f"[yellow]跳过 {preset['name']}，未填写 API Key[/yellow]")
            continue

        # base_url 覆盖
        base_url = None
        if preset["base_url"]:
            override = questionary.text(
                "base_url（留空使用默认值）：",
                default=preset["base_url"],
            ).ask()
            if override and override != preset["base_url"]:
                base_url = override
        else:
            # 自定义 provider 必须填 base_url
            while True:
                base_url = questionary.text("base_url：").ask()
                error = validate_custom_provider(key, base_url)
                if error:
                    console.print(f"[red]{error}[/red]")
                else:
                    break

        # 自定义模型
        custom_models = None
        if key in ("custom_anthropic", "custom_openai"):
            custom_models = ask_custom_models()

        selected.append((key, api_key, base_url, custom_models))

    if not selected:
        console.print("[red]没有配置任何有效的 Provider[/red]")
        return {}, {}

    providers_data, env_vars = build_providers_yaml(selected)
    return providers_data, env_vars


def ask_custom_models() -> dict:
    """询问自定义 provider 的模型列表"""
    models = {}
    while True:
        name = questionary.text("模型显示名（逻辑名，如 my-model）：").ask()
        if not name:
            break
        model_id = questionary.text("上游真实 model_id：").ask()
        input_price = questionary.text(
            "输入价格（每 1M tokens，美元）：",
            default="1.0",
        ).ask()
        output_price = questionary.text(
            "输出价格（每 1M tokens，美元）：",
            default="1.0",
        ).ask()
        models[name] = {
            "model_id": model_id,
            "input_price_per_1m": float(input_price or "0"),
            "output_price_per_1m": float(output_price or "0"),
        }
        if not questionary.confirm("是否继续添加模型？", default=False).ask():
            break
    return models


def adapt_scenario_workers(scenario_workers: list[dict], available_models: list[str]) -> list[dict]:
    """把场景预设中的 Worker 模型替换为实际可用的模型"""
    if not available_models:
        return scenario_workers

    adapted = []
    for w in scenario_workers:
        w = dict(w)
        if w["default_model"] not in available_models:
            fallback = available_models[0]
            console.print(
                f"[yellow]Worker '{w['name']}' 的默认模型 '{w['default_model']}' 不可用，"
                f"已替换为 '{fallback}'[/yellow]"
            )
            w["default_model"] = fallback
        adapted.append(w)
    return adapted


def run_setup_wizard(config_dir: str = "config", project_root: str = "."):
    """运行配置向导"""
    console.print(Panel.fit(
        "欢迎使用多模型 Agent 编排工具\n"
        "本向导会帮你配置模型服务、主工程师、子工程师和 API Key",
        title="🔧 Setup Wizard",
        border_style="cyan",
    ))

    config_path = Path(project_root) / config_dir
    config_path.mkdir(parents=True, exist_ok=True)

    providers_data, workers_data = load_existing_config(config_path)

    # 是否备份
    if (config_path / "workers.yaml").exists() or (config_path / "providers.yaml").exists():
        if questionary.confirm("检测到已有配置，是否先备份？", default=True).ask():
            backup_config(str(config_path))

    # 步骤 1：配置 Provider
    new_providers_data, env_vars = ask_providers()
    if not new_providers_data:
        return

    # 保存 providers.yaml
    providers_yaml_path = config_path / "providers.yaml"
    save_yaml(new_providers_data, providers_yaml_path)
    console.print(f"\n[green]Provider 配置已保存：{providers_yaml_path}[/green]")

    # 保存 API Key 到 .env
    if env_vars:
        save_env(env_vars, project_root)

    # 重新加载可用模型
    available_models = get_available_models(str(config_path))
    if not available_models:
        console.print("[red]没有配置任何可用模型，请重新运行 setup[/red]")
        return

    # 步骤 2：选择场景
    scenario_key = ask_scenario()
    scenario = SCENARIOS[scenario_key]

    console.print(f"\n[bold green]已选择场景：{scenario['name']}[/bold green]")
    console.print(f"[dim]{scenario['description']}[/dim]\n")

    # 适配场景预设中的模型到可用模型
    scenario_workers = adapt_scenario_workers(scenario["workers"], available_models)

    # 步骤 3：配置总指挥
    orchestrator_model = ask_orchestrator_model(
        available_models, scenario["orchestrator_model"]
    )

    # 步骤 4：配置子工程师
    workers = ask_workers(available_models, scenario_workers)

    if not workers:
        console.print("[red]至少需要配置一个子工程师[/red]")
        return

    # 步骤 5：生成 workers.yaml
    workers_yaml_data = build_workers_yaml(orchestrator_model, workers)
    workers_yaml_path = config_path / "workers.yaml"
    save_yaml(workers_yaml_data, workers_yaml_path)

    console.print(f"\n[green]配置已保存：{workers_yaml_path}[/green]")

    # 最终提示
    console.print(Rule("[bold green]配置完成[/bold green]"))
    console.print(f"总指挥模型：[bold cyan]{orchestrator_model}[/bold cyan]")
    console.print("子工程师：")
    for w in workers:
        console.print(f"  • {w['name']} ({w['key']}) → {w['default_model']}")
    console.print(f"\n现在可以运行：[bold]python run.py \"你的需求\"[/bold]")
