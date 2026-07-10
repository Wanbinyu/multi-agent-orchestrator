"""Agent 工具连接向导

简化 Provider / 模型配置流程：
1. 选择 Provider 类型
2. 输入 API Key / Base URL
3. 自动测试连通性
4. 列出可用模型并选择主模型
5. 保存配置
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import questionary
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule

from src.gateway.connection_test import check_provider_connection
from src.models.catalog import (
    BUILTIN_MODELS,
    PROVIDER_TEMPLATES,
    find_models_for_template,
    get_provider_templates,
)

console = Console()


class AgentSetupWizard:
    """Agent 连接配置向导"""

    def __init__(self, config_path: str = "config/providers.yaml"):
        self.config_path = Path(config_path)
        self.config: dict[str, Any] = {"providers": {}, "models": {}}
        self.main_model: str | None = None

    def run(self):
        """运行向导"""
        console.print(Panel.fit("🌐 欢迎使用模型连接向导", style="bold cyan"))
        console.print("本向导将帮助你连接 AI 模型服务并选择主模型。\n")

        # 加载已有配置（如果存在）
        self._load_existing()

        # 主循环：添加 Provider
        while True:
            self._add_provider()
            if not questionary.confirm("是否继续添加其他 Provider？", default=False).ask():
                break

        # 选择主模型
        if self.config["models"]:
            self._select_main_model()
        else:
            console.print("[yellow]没有可用的模型，跳过主模型选择。[/yellow]")

        # 保存配置
        self._save_config()
        self._print_summary()

    def _load_existing(self):
        """加载已有配置"""
        if not self.config_path.exists():
            return
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            self.config["providers"] = data.get("providers", {})
            self.config["models"] = data.get("models", {})
            self.main_model = data.get("main_model")
            console.print(f"[dim]已加载现有配置: {self.config_path}[/dim]\n")
        except Exception as e:
            console.print(f"[yellow]加载现有配置失败: {e}[/yellow]")

    def _add_provider(self):
        """添加一个 Provider"""
        templates = get_provider_templates()
        choices = [
            questionary.Choice(title=f"{t['name']}", value=key)
            for key, t in templates.items()
        ]

        template_key = questionary.select(
            "请选择 Provider 类型：",
            choices=choices,
        ).ask()

        if not template_key:
            return

        template = templates[template_key]
        provider_name = questionary.text(
            "给这个 Provider 起个名字（用于配置中标识）：",
            default=self._default_provider_name(template_key),
        ).ask()

        # 询问 API Key
        api_key = questionary.password(
            f"请输入 {template['name']} 的 API Key：",
        ).ask()

        # 询问 Base URL（带默认值）
        default_base_url = template.get("base_url", "")
        base_url = questionary.text(
            "Base URL（可选，留空使用默认值）：",
            default=default_base_url,
        ).ask()
        if not base_url:
            base_url = default_base_url

        # 询问超时
        timeout_str = questionary.text(
            "请求超时时间（秒）：",
            default=str(template.get("timeout", 120)),
        ).ask()
        try:
            timeout = int(timeout_str)
        except ValueError:
            timeout = 120

        # 如果是自定义 OpenAI 兼容服务，需要手动指定模型
        recommended_models = find_models_for_template(template_key)
        selected_aliases: list[str] = []

        if template_key == "custom_openai":
            console.print("\n[cyan]自定义 OpenAI 兼容服务需要手动指定模型。[/cyan]")
            model_id = questionary.text("上游真实 model_id：").ask()
            alias = questionary.text("给这个模型起个短名（如 kimi-local）：", default=model_id).ask()

            self.config["models"][alias] = {
                "provider": provider_name,
                "model_id": model_id,
                "input_price_per_1m": 0.0,
                "output_price_per_1m": 0.0,
                "capabilities": [],
            }
            selected_aliases.append(alias)
        else:
            # 从目录中选择要启用的模型
            if recommended_models:
                model_choices = [
                    questionary.Choice(
                        title=f"{m.name} ({m.default_model_id}) - {m.description}",
                        value=m.alias,
                        checked=True,
                    )
                    for m in recommended_models
                ]
                selected_aliases = questionary.checkbox(
                    "选择要启用的模型：",
                    choices=model_choices,
                ).ask() or []

            # 为选中的模型补充配置
            for alias in selected_aliases:
                entry = BUILTIN_MODELS[alias]
                self.config["models"][alias] = entry.to_model_config(provider_name)

        if not selected_aliases:
            console.print("[yellow]未选择任何模型，该 Provider 将不会生效。[/yellow]")
            return

        # 测试连通性
        test_model_id = self.config["models"][selected_aliases[0]]["model_id"]
        console.print(f"\n[dim]正在测试 {template['name']} 连接...[/dim]")
        result = check_provider_connection(
            provider_type=template["type"],
            api_key=api_key,
            base_url=base_url,
            model_id=test_model_id,
            timeout=30,
        )

        if not result.success:
            console.print(f"[red]❌ 连接测试失败：{result.error_message}[/red]")
            if not questionary.confirm("是否仍要保存这个 Provider 配置？", default=False).ask():
                # 回滚本次添加的模型
                for alias in selected_aliases:
                    self.config["models"].pop(alias, None)
                return
        else:
            console.print(
                f"[green]✅ 连接成功！响应时间 {result.response_time_ms:.0f}ms[/green]"
            )

        # 保存 Provider 配置
        self.config["providers"][provider_name] = {
            "name": template["name"],
            "type": template["type"],
            "base_url": base_url,
            "api_keys": [f"${{{self._env_var_name(provider_name)}}}"],
            "timeout": timeout,
            "rpm_limit": template.get("rpm_limit", 60),
        }

        # 保存 API Key 到 .env
        self._save_api_key_to_env(provider_name, api_key)
        console.print(f"[green]✅ Provider '{provider_name}' 已保存[/green]\n")

    def _select_main_model(self):
        """选择主模型"""
        console.print(Rule("[bold cyan]选择主模型[/bold cyan]"))
        choices = [
            questionary.Choice(
                title=f"{alias} ({cfg['model_id']}) - {cfg['provider']}",
                value=alias,
            )
            for alias, cfg in self.config["models"].items()
        ]

        default = self.main_model
        if default not in self.config["models"]:
            default = None

        self.main_model = questionary.select(
            "请选择主模型（将用于对话和任务拆分）：",
            choices=choices,
            default=default,
        ).ask()

    def _save_config(self):
        """保存 providers.yaml"""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

        output = {
            "main_model": self.main_model,
            "providers": self.config["providers"],
            "models": self.config["models"],
        }

        with open(self.config_path, "w", encoding="utf-8") as f:
            yaml.dump(output, f, allow_unicode=True, sort_keys=False, default_flow_style=False)

    def _save_api_key_to_env(self, provider_name: str, api_key: str):
        """将 API Key 保存到 .env 文件"""
        env_path = Path(".env")
        env_var = self._env_var_name(provider_name)
        line = f"{env_var}={api_key}\n"

        existing_lines: list[str] = []
        if env_path.exists():
            with open(env_path, "r", encoding="utf-8") as f:
                existing_lines = f.readlines()

        # 更新或追加
        found = False
        new_lines = []
        for existing_line in existing_lines:
            if existing_line.startswith(f"{env_var}="):
                new_lines.append(line)
                found = True
            else:
                new_lines.append(existing_line)

        if not found:
            new_lines.append(line)

        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)

    def _default_provider_name(self, template_key: str) -> str:
        """生成默认 Provider 名"""
        base = template_key.replace("_", "")
        name = base
        counter = 1
        while name in self.config["providers"]:
            name = f"{base}{counter}"
            counter += 1
        return name

    def _env_var_name(self, provider_name: str) -> str:
        """生成环境变量名"""
        return f"{provider_name.upper()}_API_KEY"

    def _print_summary(self):
        """打印配置摘要"""
        console.print(Rule("[bold green]配置完成[/bold green]"))
        console.print(f"[green]配置已保存到：{self.config_path}[/green]")
        console.print(f"[green]主模型：{self.main_model}[/green]")
        console.print("\n已连接 Provider：")
        for name, cfg in self.config["providers"].items():
            console.print(f"  • {name}: {cfg['name']} ({cfg['base_url']})")
        console.print("\n可用模型：")
        for alias, cfg in self.config["models"].items():
            marker = " ⭐" if alias == self.main_model else ""
            console.print(f"  • {alias}{marker} → {cfg['model_id']}")


def main():
    wizard = AgentSetupWizard()
    wizard.run()


if __name__ == "__main__":
    main()
