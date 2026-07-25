"""CLI 入口"""
from __future__ import annotations

import sys
import json
from pathlib import Path

# Windows 默认控制台编码（如 GBK）无法输出 emoji，先强制使用 UTF-8
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel

from src.cli.agent_setup import AgentSetupWizard
from src.cli.chat_command import run_chat_loop
from src.cli.setup_wizard import run_setup_wizard
from src.core.dispatcher import Dispatcher
from src.core.memory import MemoryContextBuilder, MemoryStore
from src.core.orchestrator import Orchestrator
from src.core.reviewer import Reviewer
from src.core.session import SessionStore
from src.core.worker import Worker, load_workers_config
from src.gateway.client import GatewayClient
from src.tools.file_tools import write_text_file
from src.version import __version__

# 加载 .env 文件
load_dotenv()

app = typer.Typer(
    help="多模型 Agent 编排工具 CLI",
    invoke_without_command=True,
    no_args_is_help=False,
)
console = Console()


@app.callback()
def app_callback(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        help="显示版本并退出",
        is_eager=True,
    ),
) -> None:
    if version:
        typer.echo(f"MAO {__version__}")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        _run_default_cli()


def _run_agent_setup(config_dir: str = "config") -> None:
    wizard = AgentSetupWizard(config_path=f"{config_dir}/providers.yaml")
    wizard.run()
    load_dotenv(override=True)


def _run_chat(session: str | None = None, config_dir: str = "config") -> None:
    gateway = GatewayClient(config_path=f"{config_dir}/providers.yaml")
    store = SessionStore(base_dir="sessions")
    run_chat_loop(gateway, store, session_id=session)


def _run_default_cli(config_dir: str = "config") -> None:
    """Make `mao` the normal interactive entry point, including first-run setup."""
    config_path = Path(config_dir) / "providers.yaml"
    if not config_path.exists():
        if not _has_interactive_console():
            console.print(
                "[yellow]尚未配置 Provider。请在交互式终端运行 `mao`，"
                "或使用 `mao web` 打开配置界面。[/yellow]"
            )
            raise typer.Exit(code=2)
        console.print("[cyan]首次运行：先连接一个模型服务。[/cyan]")
        _run_agent_setup(config_dir)
        if not config_path.exists():
            console.print("[yellow]未生成 Provider 配置，已退出。[/yellow]")
            raise typer.Exit(code=1)
    _run_chat(config_dir=config_dir)


def _has_interactive_console() -> bool:
    """Require both input and output terminals before launching a prompt UI."""
    try:
        return bool(sys.stdin.isatty() and sys.stdout.isatty())
    except (AttributeError, OSError):
        return False


@app.command()
def setup(
    config_dir: str = typer.Option("config", "--config", "-c", help="配置目录"),
):
    """运行旧版交互式配置向导（生成 workers.yaml）"""
    project_root = Path.cwd()
    run_setup_wizard(config_dir=config_dir, project_root=str(project_root))


@app.command()
def agent_setup(
    config_dir: str = typer.Option("config", "--config", "-c", help="配置目录"),
):
    """运行新版 Agent 连接向导（配置 Provider 和主模型）"""
    _run_agent_setup(config_dir)


@app.command()
def chat(
    session: str = typer.Option(None, "--session", "-s", help="会话 ID，不指定则创建新会话"),
    config_dir: str = typer.Option("config", "--config", "-c", help="配置目录"),
):
    """进入交互式多轮对话"""
    _run_chat(session=session, config_dir=config_dir)


@app.command()
def web(
    host: str = typer.Option("127.0.0.1", "--host", help="监听地址"),
    port: int = typer.Option(8123, "--port", help="监听端口"),
    no_open: bool = typer.Option(False, "--no-open", help="不自动打开浏览器"),
):
    """启动本地 WebUI"""
    from src.ui.cli import serve

    serve(host=host, port=port, open_browser=not no_open)


@app.command(hidden=True)
def benchmark_agent(
    instruction: str = typer.Option(..., "--instruction", help="Benchmark task instruction"),
    project_root: str = typer.Option(".", "--project-root", help="Isolated task workspace"),
    config_dir: str = typer.Option("config", "--config", "-c", help="Provider config directory"),
    state_dir: str = typer.Option(".mao-benchmark", "--state-dir", help="Benchmark state directory"),
    result_path: str = typer.Option("", "--result", help="Optional machine-readable result path"),
    strategy: str = typer.Option("auto-route", "--strategy", help="fixed-single, auto-route, or multi-model"),
    execution_depth: str = typer.Option("standard", "--execution-depth", help="fast, standard, or deep"),
    main_model: str = typer.Option("", "--main-model", help="Configured MAO model alias"),
    allowed_models: str = typer.Option("", "--allowed-models", help="Comma-separated model aliases"),
):
    """Run one controlled, non-interactive benchmark turn."""
    from src.core.engineering.benchmark_agent import run_headless_benchmark_agent_sync

    if strategy not in {"fixed-single", "auto-route", "multi-model"}:
        raise typer.BadParameter("策略必须是 fixed-single、auto-route 或 multi-model")
    if execution_depth not in {"auto", "fast", "standard", "deep"}:
        raise typer.BadParameter("执行深度必须是 auto、fast、standard 或 deep")
    result = run_headless_benchmark_agent_sync(
        instruction,
        project_root=project_root,
        config_dir=config_dir,
        state_dir=state_dir,
        strategy=strategy,
        execution_depth=execution_depth,
        main_model=main_model,
        allowed_models=[item.strip() for item in allowed_models.split(",") if item.strip()],
    )
    payload = json.dumps(result.model_dump(), ensure_ascii=False, indent=2)
    if result_path:
        target = Path(result_path).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(payload + "\n", encoding="utf-8")
    typer.echo(payload)


@app.command()
def run(
    request: str = typer.Argument(..., help="一句话开发需求，例如：开发一个登录页面"),
    output_dir: str = typer.Option("output", "--output", "-o", help="输出目录"),
    config_dir: str = typer.Option("config", "--config", "-c", help="配置目录"),
    max_workers: int = typer.Option(4, "--max-workers", "-w", help="最大并发 Worker 数"),
    orchestrator_model: str = typer.Option(None, "--orchestrator-model", "-m", help="指定总指挥模型，例如 glm-ark"),
    assume_yes: bool = typer.Option(False, "--yes", "-y", help="跳过执行前的确认提示，直接执行"),
    output_format: str = typer.Option(
        "plain", "--output-format", help="输出格式：plain|json|streaming-json（后两者为无头事件流）"
    ),
):
    """运行多模型 Agent 编排流程"""
    from src.core.run_events import RunEventWriter, build_usage

    if output_format not in {"plain", "json", "streaming-json"}:
        raise typer.BadParameter(
            "必须是 plain、json 或 streaming-json",
            param_hint="--output-format",
        )
    writer = RunEventWriter(output_format)
    plain = output_format == "plain"
    exit_code = 0
    status = "completed"
    gateway = None

    def emit_task_progress(event_type: str, payload: dict) -> None:
        """将 Dispatcher 进度转换为稳定且不包含 Worker 正文的事件。"""
        if event_type == "task_start":
            writer.emit("model", {
                "phase": "started",
                **_task_event_metadata(payload),
            })
            return
        if event_type == "task_retry":
            writer.emit("error", {
                "kind": "task_retry",
                **_task_event_metadata(payload),
                "attempt": payload.get("attempt"),
                "max_attempts": payload.get("max_attempts"),
                "previous_error": payload.get("previous_error", ""),
            })
            return
        if event_type != "task_complete":
            writer.emit(event_type, payload)
            return

        metadata = _task_event_metadata(payload)
        writer.emit("model", {
            "phase": "completed",
            **metadata,
            "success": bool(payload.get("success")),
            "attempts": payload.get("attempts", 1),
        })
        for index, tool_call in enumerate(payload.get("tool_calls") or [], start=1):
            tool_name = str(tool_call.get("tool") or tool_call.get("name") or "unknown")
            tool_event = {
                "task_id": payload.get("id", ""),
                "index": index,
                "tool": tool_name,
                "success": bool(tool_call.get("success", True)),
            }
            if tool_name == "run_command":
                writer.emit("command", tool_event)
            else:
                writer.emit("tool", tool_event)
        files_written = list(payload.get("files_written") or [])
        if files_written:
            writer.emit("file_change", {
                "task_id": payload.get("id", ""),
                "paths": files_written,
            })
        evidence = list(payload.get("acceptance_evidence") or [])
        if evidence:
            writer.emit("verification", {
                "task_id": payload.get("id", ""),
                "passed": bool(payload.get("success")),
                "evidence": evidence,
            })
        if not payload.get("success"):
            writer.emit("error", {
                "kind": "task_failed",
                **metadata,
                "error": payload.get("error", ""),
            })

    try:
        writer.emit("run", {
            "request": request, "output_dir": output_dir,
            "config_dir": config_dir, "version": __version__,
        })
        if plain:
            console.print(Panel.fit(f"🚀 开始处理需求：\n{request}", title="Multi-Agent Orchestrator"))

        # 初始化网关与记忆
        gateway = GatewayClient(config_path=f"{config_dir}/providers.yaml")
        memory_store = MemoryStore(config_path=f"{config_dir}/memory.yaml")
        memory_context = ""
        if memory_store.config.enabled:
            memory_context = MemoryContextBuilder(memory_store).build_context(request)

        # 总工拆任务
        if plain:
            console.print("\n[bold cyan]🧠 Orchestrator 正在分析需求...[/bold cyan]")
        orchestrator = Orchestrator(
            gateway,
            config_path=f"{config_dir}/workers.yaml",
            model_override=orchestrator_model,
        )
        plan = orchestrator.plan(request, memory_context=memory_context)

        writer.emit("plan", {
            "summary": plan.summary,
            "tasks": [
                {"id": t.id, "type": t.type, "title": t.title,
                 "assigned_model": t.assigned_model, "execution_mode": t.execution_mode}
                for t in plan.tasks
            ],
        })
        for task in plan.tasks:
            writer.emit("model", {
                "phase": "planned",
                "task_id": task.id,
                "role": task.frontend_stage or task.type,
                "model": task.assigned_model,
            })

        if plain:
            console.print(f"\n[bold green]📋 拆分为 {len(plan.tasks)} 个子任务：[/bold green]")
            for task in plan.tasks:
                console.print(f"  • [{task.type}] {task.title} → {task.assigned_model}")

        # 执行前确认：交互式终端且未传 --yes 时，征求用户同意
        if not assume_yes and sys.stdin.isatty():
            console.print(
                f"\n[bold yellow]即将执行 {len(plan.tasks)} 个子任务并自动写入文件到 {output_dir}[/bold yellow]"
            )
            answer = console.input("允许执行？(y/n)：")
            if answer.strip().lower() not in ("y", "yes", "是", "允许"):
                console.print("[dim]已取消[/dim]")
                status = "cancelled"
                writer.emit("approval", {"approved": False, "mode": "interactive"})
                return
            writer.emit("approval", {"approved": True, "mode": "interactive"})
        else:
            writer.emit("approval", {
                "approved": True,
                "mode": "auto" if assume_yes else "non_interactive",
            })

        # 并发执行
        if plain:
            console.print("\n[bold cyan]⚙️ Worker 开始并发执行...[/bold cyan]")
        workers_config = load_workers_config(f"{config_dir}/workers.yaml")
        worker = Worker(gateway, workers_config)
        dispatcher = Dispatcher(worker, max_workers=max_workers)
        dispatch_kwargs = {
            "output_dir": output_dir,
            "memory_context": memory_context,
        }
        if not plain:
            dispatch_kwargs["progress_callback"] = emit_task_progress
        results = dispatcher.dispatch(plan, **dispatch_kwargs)
        if any(not result.success for result in results):
            exit_code = 1
        if not plain:
            for result in results:
                if result.response is None:
                    continue
                writer.emit("model", {
                    "phase": "usage",
                    "task_id": result.task.id,
                    "role": result.task.frontend_stage or result.task.type,
                    "model": result.response.model,
                    "provider": result.response.provider,
                    "input_tokens": result.response.input_tokens,
                    "output_tokens": result.response.output_tokens,
                    "cost_usd": result.response.cost_usd,
                })

        # 汇总结果
        if plain:
            console.print("\n[bold green]📁 输出文件：[/bold green]")
            for result in results:
                if result.success:
                    for f in result.files_written:
                        console.print(f"  ✓ {f}")

        # 保存原始结果汇总
        summary_text = build_summary(plan, results)
        summary_path = write_text_file("summary.md", summary_text, output_dir)
        if plain:
            console.print(f"\n[bold]📄 汇总报告：[/bold] {summary_path}")

        # Reviewer 审查收口
        if plain:
            console.print("\n[bold cyan]🔍 Reviewer 正在审查结果...[/bold cyan]")
        reviewer = Reviewer(gateway, config_path=f"{config_dir}/workers.yaml")
        review = reviewer.review(request, plan, results)

        review_text = build_review_section(review)
        write_text_file("summary.md", review_text, output_dir, append=True)
        writer.emit("verification", {
            "kind": "review",
            "passed": review.passed,
            "issues": review.issues,
        })

        if review.passed:
            if plain:
                console.print("[bold green]✅ Reviewer 审查通过[/bold green]")
        else:
            exit_code = 1
            writer.emit("error", {
                "kind": "review_failed",
                "issues": review.issues,
            })
            if plain:
                console.print("[bold yellow]⚠️ Reviewer 发现问题[/bold yellow]")
        if review.issues:
            if plain:
                for issue in review.issues:
                    console.print(f"  - {issue}")
        if review.final_output:
            if plain:
                console.print("\n[bold green]📝 最终整合输出：[/bold green]")
                console.print(review.final_output[:1000] + ("..." if len(review.final_output) > 1000 else ""))

        if plain:
            gateway.print_billing()
        if exit_code:
            status = "failed"
            raise typer.Exit(code=exit_code)
    except typer.Exit:
        raise
    except Exception as exc:
        exit_code = 1
        status = "failed"
        writer.emit("error", {"kind": "run_failed", "error": str(exc)})
        raise
    finally:
        billing = {}
        if gateway is not None:
            summary = gateway.billing.summary()
            billing = summary if isinstance(summary, dict) else {}
        if not writer.ended:
            writer.emit("usage", build_usage(billing))
            writer.emit("end", {
                "status": status,
                "exit_code": exit_code,
                "elapsed_ms": writer.elapsed_ms(),
            })
        writer.finish({
            "status": status,
            "exit_code": exit_code,
            "elapsed_ms": writer.elapsed_ms(),
        })


def _task_event_metadata(payload: dict) -> dict:
    """保留任务事件的可审计元数据，避免输出 Worker 正文或工具结果正文。"""
    keys = ("id", "type", "title", "assigned_model", "execution_mode")
    return {key: payload[key] for key in keys if key in payload}


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


plugin_app = typer.Typer(help="管理 MAO 插件（发现、诊断、启用、禁用）")


class _ThrowawayPresets:
    """``mao plugin doctor`` 用的临时预设注册表，避免污染真实注册中心。"""

    def __init__(self) -> None:
        self.presets: dict[str, dict] = {}

    def register_preset(self, key: str, preset: dict) -> None:
        self.presets[key] = preset

    def unregister_preset(self, key: str) -> None:
        self.presets.pop(key, None)


@plugin_app.command("list")
def plugin_list(
    config_dir: str = typer.Option("config", "--config", "-c", help="配置目录"),
):
    """列出已发现的插件及其启用态、能力与权限"""
    from src.plugins.runtime import new_plugin_manager

    mgr = new_plugin_manager(config_dir)
    statuses = mgr.list_status()
    if not statuses:
        console.print("未发现插件。安装声明 mao.plugins entry point 的包后再试。")
        return
    console.print("[bold]已发现插件：[/bold]")
    for s in statuses:
        compat = "兼容" if s["api_compatible"] else f"不兼容(API {s['mao_api_version']})"
        enabled = "已启用" if s["enabled"] else "未启用"
        console.print(
            f"  • [bold]{s['id']}[/bold] {s['name']} v{s['version']} "
            f"[{enabled}] [{compat}]"
        )
        if s["capabilities"]:
            console.print(f"      能力：{', '.join(s['capabilities'])}")
        if s["permissions"]:
            console.print(f"      权限：{', '.join(s['permissions'])}")
        if s["source"]:
            console.print(f"      来源：{s['source']}")


@plugin_app.command("doctor")
def plugin_doctor(
    config_dir: str = typer.Option("config", "--config", "-c", help="配置目录"),
):
    """诊断插件发现、兼容与加载健康（不影响运行中的工具注册表）"""
    from src.plugins.manager import PluginManager
    from src.tools.registry import ToolRegistry

    mgr = PluginManager(
        ToolRegistry(), preset_registry=_ThrowawayPresets(), config_dir=config_dir
    )
    mgr.discover()
    result = mgr.load_enabled()
    console.print(
        f"发现 {result.discovered}，加载 {result.loaded}，"
        f"不兼容 {result.rejected_incompatible}，未启用 {result.skipped_disabled}，"
        f"失败 {result.failed}"
    )
    if result.loaded_ids:
        console.print(f"[green]已加载：{', '.join(result.loaded_ids)}[/green]")
    for d in result.diagnostics:
        entry = d.get("entry") or d.get("source", "plugin")
        console.print(f"  - [yellow]{entry}[/yellow]: {d['message']}；{d['action']}")
    if not result.diagnostics and result.failed == 0:
        console.print("[green]插件诊断无异常。[/green]")


@plugin_app.command("enable")
def plugin_enable(
    plugin_id: str = typer.Argument(..., help="插件 id"),
    config_dir: str = typer.Option("config", "--config", "-c", help="配置目录"),
):
    """启用一个插件（下次启动 mao 时加载）"""
    from src.plugins.runtime import new_plugin_manager

    mgr = new_plugin_manager(config_dir)
    mgr.enable(plugin_id)
    discovered_ids = {s["id"] for s in mgr.list_status()}
    if discovered_ids and plugin_id not in discovered_ids:
        console.print(
            f"[yellow]已记录启用 {plugin_id}，但当前未发现该插件；安装后将自动加载。[/yellow]"
        )
    else:
        console.print(f"[green]已启用插件 {plugin_id}（下次启动 mao 时加载）[/green]")


@plugin_app.command("disable")
def plugin_disable(
    plugin_id: str = typer.Argument(..., help="插件 id"),
    config_dir: str = typer.Option("config", "--config", "-c", help="配置目录"),
):
    """禁用一个插件"""
    from src.plugins.runtime import new_plugin_manager

    mgr = new_plugin_manager(config_dir)
    mgr.disable(plugin_id)
    console.print(f"[green]已禁用插件 {plugin_id}[/green]")


app.add_typer(plugin_app, name="plugin")


def _maybe_insert_run_subcommand(argv: list[str]) -> list[str]:
    """如果没有显式指定子命令，默认插入 run 子命令"""
    known_commands = {
        "setup", "agent-setup", "chat", "web", "run", "benchmark-agent", "plugin",
        "--help", "-h", "--version",
    }
    if len(argv) > 1 and argv[1] not in known_commands:
        argv.insert(1, "run")
    return argv


def main() -> None:
    """Console-script and source checkout entry point."""
    sys.argv = _maybe_insert_run_subcommand(sys.argv)
    app()


if __name__ == "__main__":
    main()
