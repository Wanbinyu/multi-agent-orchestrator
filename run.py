"""CLI 入口"""
from __future__ import annotations

import os
from pathlib import Path

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel

from src.cli.agent_setup import AgentSetupWizard
from src.cli.setup_wizard import run_setup_wizard
from src.core.dispatcher import Dispatcher
from src.core.orchestrator import Orchestrator
from src.core.reviewer import Reviewer
from src.core.worker import Worker, load_workers_config
from src.gateway.client import GatewayClient
from src.tools.file_tools import write_text_file

# 加载 .env 文件
load_dotenv()

app = typer.Typer(help="多模型 Agent 编排工具 CLI")
console = Console()


@app.command()
def setup(
    config_dir: str = typer.Option("config", "--config", "-c", help="配置目录"),
):
    """运行旧版交互式配置向导（生成 workers.yaml）"""
    project_root = Path(__file__).parent
    os.chdir(project_root)
    run_setup_wizard(config_dir=config_dir, project_root=str(project_root))


@app.command()
def agent_setup(
    config_dir: str = typer.Option("config", "--config", "-c", help="配置目录"),
):
    """运行新版 Agent 连接向导（配置 Provider 和主模型）"""
    project_root = Path(__file__).parent
    os.chdir(project_root)
    wizard = AgentSetupWizard(config_path=f"{config_dir}/providers.yaml")
    wizard.run()


@app.command()
def run(
    request: str = typer.Argument(..., help="一句话开发需求，例如：开发一个登录页面"),
    output_dir: str = typer.Option("output", "--output", "-o", help="输出目录"),
    config_dir: str = typer.Option("config", "--config", "-c", help="配置目录"),
    max_workers: int = typer.Option(4, "--max-workers", "-w", help="最大并发 Worker 数"),
    orchestrator_model: str = typer.Option(None, "--orchestrator-model", "-m", help="指定总指挥模型，例如 glm-ark"),
):
    """运行多模型 Agent 编排流程"""
    # 切换到项目根目录（兼容从任意位置运行）
    project_root = Path(__file__).parent
    os.chdir(project_root)

    console.print(Panel.fit(f"🚀 开始处理需求：\n{request}", title="Multi-Agent Orchestrator"))

    # 初始化网关
    gateway = GatewayClient(config_path=f"{config_dir}/providers.yaml")

    # 总工拆任务
    console.print("\n[bold cyan]🧠 Orchestrator 正在分析需求...[/bold cyan]")
    orchestrator = Orchestrator(
        gateway,
        config_path=f"{config_dir}/workers.yaml",
        model_override=orchestrator_model,
    )
    plan = orchestrator.plan(request)

    console.print(f"\n[bold green]📋 拆分为 {len(plan.tasks)} 个子任务：[/bold green]")
    for task in plan.tasks:
        console.print(f"  • [{task.type}] {task.title} → {task.assigned_model}")

    # 并发执行
    console.print("\n[bold cyan]⚙️ Worker 开始并发执行...[/bold cyan]")
    workers_config = load_workers_config(f"{config_dir}/workers.yaml")
    worker = Worker(gateway, workers_config)
    dispatcher = Dispatcher(worker, max_workers=max_workers)
    results = dispatcher.dispatch(plan, output_dir=output_dir)

    # 汇总结果
    console.print("\n[bold green]📁 输出文件：[/bold green]")
    for result in results:
        if result.success:
            for f in result.files_written:
                console.print(f"  ✓ {f}")

    # 保存原始结果汇总
    summary_text = build_summary(plan, results)
    summary_path = write_text_file("summary.md", summary_text, output_dir)
    console.print(f"\n[bold]📄 汇总报告：[/bold] {summary_path}")

    # Reviewer 审查收口
    console.print("\n[bold cyan]🔍 Reviewer 正在审查结果...[/bold cyan]")
    reviewer = Reviewer(gateway, config_path=f"{config_dir}/workers.yaml")
    review = reviewer.review(request, plan, results)

    review_text = build_review_section(review)
    write_text_file("summary.md", review_text, output_dir, append=True)

    if review.passed:
        console.print("[bold green]✅ Reviewer 审查通过[/bold green]")
    else:
        console.print("[bold yellow]⚠️ Reviewer 发现问题[/bold yellow]")
    if review.issues:
        for issue in review.issues:
            console.print(f"  - {issue}")
    if review.final_output:
        console.print("\n[bold green]📝 最终整合输出：[/bold green]")
        console.print(review.final_output[:1000] + ("..." if len(review.final_output) > 1000 else ""))

    # 打印计费
    gateway.print_billing()


def build_summary(plan, results) -> str:
    lines = [f"# 任务执行报告\n", f"**需求总览**：{plan.summary}\n", "## 子任务结果\n"]
    for result in results:
        lines.append(f"### [{result.task.type}] {result.task.title}\n")
        lines.append(f"- **模型**：{result.task.assigned_model}\n")
        lines.append(f"- **状态**：{'成功' if result.success else '失败'}\n")
        if not result.success:
            lines.append(f"- **错误**：{result.error}\n")
        else:
            lines.append(f"- **输出文件**：{', '.join(result.files_written) or '无'}\n")
            lines.append(f"- **Token**：输入 {result.response.input_tokens} / 输出 {result.response.output_tokens}\n")
            lines.append(f"- **成本**：${result.response.cost_usd:.6f}\n")
        lines.append("\n")
    return "\n".join(lines)


def build_review_section(review) -> str:
    lines = ["\n\n# Reviewer 审查结论\n"]
    lines.append(f"**审查结果**：{'通过' if review.passed else '未通过'}\n")
    if review.issues:
        lines.append("**问题列表**：\n")
        for issue in review.issues:
            lines.append(f"- {issue}\n")
    if review.final_output:
        lines.append("\n**最终整合输出**：\n")
        lines.append(review.final_output)
        lines.append("\n")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys

    # 如果没有显式指定子命令，默认执行 run 命令
    known_commands = {"setup", "agent-setup", "--help", "-h", "--version"}
    if len(sys.argv) > 1 and sys.argv[1] not in known_commands:
        sys.argv.insert(1, "run")

    app()
