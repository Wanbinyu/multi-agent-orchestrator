"""CLI 交互式对话命令"""
from __future__ import annotations

import asyncio
import time
from collections import Counter, defaultdict
from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.shortcuts import CompleteStyle
from rich.console import Console, Group
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

from src.core.agent import Agent
from src.core.memory import MemoryStore
from src.core.session import SessionStore
from src.gateway.client import GatewayClient


console = Console()


SLASH_COMMANDS: list[tuple[str, str, str]] = [
    ("/new", "/new [标题]", "创建新会话"),
    ("/load", "/load <id>", "加载已有会话"),
    ("/save", "/save", "保存当前会话"),
    ("/sessions", "/sessions", "列出最近会话"),
    ("/runs", "/runs [run_id]", "本地查看本会话工程运行记录"),
    ("/context", "/context", "显示上下文预算与自动压缩状态"),
    ("/tree", "/tree [路径] [深度]", "零 token 显示项目结构"),
    ("/plan", "/plan <需求>", "执行一次性多模型任务计划"),
    ("/memory add", "/memory add <分类> <内容>", "添加长期记忆"),
    ("/memory list", "/memory list [分类]", "列出长期记忆"),
    ("/memory search", "/memory search <查询>", "搜索长期记忆"),
    ("/memory forget", "/memory forget <id>", "删除长期记忆"),
    ("/memory index", "/memory index", "重建项目文件索引"),
    ("/memory summarize", "/memory summarize", "总结当前会话并保存到记忆"),
    ("/mode", "/mode <auto|approve|readonly>", "切换权限模式"),
    ("/auto", "/auto", "自动执行工具"),
    ("/approve", "/approve", "每次执行前确认"),
    ("/readonly", "/readonly", "只读模式"),
    ("/tools", "/tools", "显示模型可用工具"),
    ("/test-models", "/test-models", "测试模型连接（少量 token）"),
    ("/help", "/help", "显示完整命令帮助"),
    ("/exit", "/exit", "保存并退出"),
    ("/quit", "/quit", "保存并退出"),
]


def _build_commands_help() -> str:
    lines = ["可用命令："]
    width = max(len(usage) for _, usage, _ in SLASH_COMMANDS)
    for _, usage, description in SLASH_COMMANDS:
        lines.append(f"  {usage.ljust(width)}  {description}")
    lines.extend([
        "",
        "提示：",
        "  - 输入 / 可打开命令列表，继续输入会实时过滤",
        "  - Shift+Tab 可快速切换权限模式",
        "  - 权限询问时输入 auto/always 可切换到自动模式并批准当前请求",
    ])
    return "\n".join(lines)


COMMANDS = _build_commands_help()


class SlashCommandCompleter(Completer):
    """仅在输入以 / 开头时显示命令，并按当前文本前缀实时过滤。"""

    def get_completions(self, document: Document, complete_event):
        text = document.text_before_cursor
        if not text.startswith("/") or "\n" in text:
            return

        normalized = text.lower()
        for command, usage, description in SLASH_COMMANDS:
            if command.startswith(normalized):
                yield Completion(
                    command,
                    start_position=-len(text),
                    display=usage,
                    display_meta=description,
                )


MODES = ["auto", "approve", "readonly"]


def _summarize_params(params: dict) -> str:
    """把工具参数摘要成单行展示文本，优先关键字段"""
    for key in ("path", "command", "url", "query"):
        value = params.get(key)
        if value:
            return str(value)
    if not params:
        return ""
    return ", ".join(f"{k}={v}" for k, v in params.items())


_TOOL_PHASES: dict[str, tuple[str, str]] = {
    "project_tree": ("explore", "探索项目"),
    "git_status": ("explore", "探索项目"),
    "list_dir": ("explore", "探索项目"),
    "glob_files": ("explore", "探索项目"),
    "read_file": ("explore", "探索项目"),
    "grep_content": ("search", "检索代码"),
    "search_project_files": ("search", "检索代码"),
    "search_memory": ("search", "检索上下文"),
    "web_search": ("research", "查询资料"),
    "fetch_url": ("research", "查询资料"),
    "write_file": ("change", "生成交付物"),
    "run_command": ("execute", "执行验证"),
}


def _tool_phase(tool_name: str) -> tuple[str, str]:
    return _TOOL_PHASES.get(tool_name, ("other", "执行工具"))


def _format_tool_action(tool_name: str, params: dict[str, Any]) -> str:
    """把工具调用转成人类可读的动作描述。"""
    target = _summarize_params(params)
    labels = {
        "list_dir": "浏览目录",
        "project_tree": "生成项目树",
        "git_status": "检查 Git 状态",
        "glob_files": "匹配文件",
        "read_file": "读取文件",
        "grep_content": "搜索内容",
        "search_project_files": "搜索项目",
        "search_memory": "搜索记忆",
        "web_search": "搜索网页",
        "fetch_url": "读取网页",
        "write_file": "写入文件",
        "run_command": "运行命令",
    }
    label = labels.get(tool_name, tool_name)
    if tool_name == "write_file":
        lines = len(str(params.get("content", "")).splitlines())
        suffix = f"（{lines} 行）" if lines else ""
        return f"{label} {target or '未指定路径'}{suffix}"
    return f"{label} {target}".rstrip()


def _progress_message(counts: Counter[str]) -> str:
    directories = counts["list_dir"] + counts["project_tree"]
    files = counts["read_file"]
    searches = sum(counts[name] for name in ("glob_files", "grep_content", "search_project_files"))
    writes = counts["write_file"]
    commands = counts["run_command"]
    if writes:
        return f"📝 正在整理交付物 · {writes} 个文件"
    if commands:
        return f"🧪 正在验证 · {commands} 条命令"
    parts = []
    if directories:
        parts.append(f"{directories} 个目录")
    if files:
        parts.append(f"{files} 个文件")
    if searches:
        parts.append(f"{searches} 次检索")
    detail = " / ".join(parts)
    return f"🔎 正在分析项目{' · ' + detail if detail else ''}"


def _summarize_tool_activity(tool_calls: list[dict[str, Any]]) -> list[str]:
    """生成稳定、紧凑的本轮工作摘要。"""
    counts: Counter[str] = Counter()
    unique_targets: dict[str, set[str]] = defaultdict(set)
    completed_targets: dict[str, set[str]] = defaultdict(set)
    failed: list[dict[str, Any]] = []
    cache_hits = 0
    skipped = 0
    for call in tool_calls:
        tool_name = str(call.get("tool", "unknown"))
        counts[tool_name] += 1
        target = _summarize_params(call.get("params", {}) or {})
        unique_targets[tool_name].add(target)
        if not call.get("success"):
            failed.append(call)
        elif call.get("skipped"):
            skipped += 1
        else:
            completed_targets[tool_name].add(target)
        if call.get("cached"):
            cache_hits += 1

    lines: list[str] = []
    if counts["project_tree"] or counts["list_dir"] or counts["read_file"]:
        tree_text = (
            f"生成 {counts['project_tree']} 次项目树，"
            if counts["project_tree"]
            else ""
        )
        lines.append(
            f"探索：{tree_text}"
            f"浏览 {len(completed_targets['list_dir'])} 个目录，"
            f"读取 {len(completed_targets['read_file'])} 个文件"
        )
    if counts["git_status"]:
        lines.append(f"版本：检查 {counts['git_status']} 次 Git 工作区状态")
    search_count = sum(counts[name] for name in ("glob_files", "grep_content", "search_project_files", "search_memory"))
    if search_count:
        lines.append(f"检索：执行 {search_count} 次代码或上下文搜索")
    if counts["run_command"]:
        lines.append(f"验证：运行 {counts['run_command']} 条命令")
    if counts["write_file"]:
        lines.append(f"变更：写入 {len(unique_targets['write_file'])} 个文件")

    duplicate_count = sum(counts.values()) - sum(len(values) for values in unique_targets.values())
    if duplicate_count:
        lines.append(f"折叠：{duplicate_count} 次重复操作未逐条展示")
    if cache_hits:
        lines.append(f"缓存：{cache_hits} 次只读操作直接复用本轮结果")
    if skipped:
        lines.append(f"抽样：{skipped} 次超出读取上限的请求已跳过")
    success_count = len(tool_calls) - len(failed) - skipped
    lines.append(f"状态：{success_count} 次成功，{len(failed)} 次失败，{skipped} 次跳过")
    for call in failed[:3]:
        lines.append(
            f"失败：{_format_tool_action(str(call.get('tool', 'unknown')), call.get('params', {}) or {})}"
            f" · {call.get('error') or '未知错误'}"
        )
    return lines


def _mode_color(mode: str) -> str:
    """返回模式对应的 prompt_toolkit HTML 颜色名"""
    if mode == "auto":
        return "ansired"
    if mode == "approve":
        return "ansiyellow"
    return "ansigreen"


def _mode_rich_style(mode: str) -> str:
    """返回模式对应的 Rich 样式"""
    if mode == "auto":
        return "bold red"
    if mode == "approve":
        return "bold yellow"
    return "bold green"


def _make_prompt_session(mode_ref: list[str]) -> PromptSession:
    """创建支持 Shift+Tab 切换模式的 prompt_toolkit 会话"""
    kb = KeyBindings()

    @kb.add(Keys.BackTab)
    def _switch_mode(event):
        idx = MODES.index(mode_ref[0])
        mode_ref[0] = MODES[(idx + 1) % len(MODES)]
        event.app.invalidate()

    return PromptSession(
        key_bindings=kb,
        completer=SlashCommandCompleter(),
        complete_while_typing=True,
        complete_style=CompleteStyle.COLUMN,
        bottom_toolbar=lambda: HTML(
            f" Mode: <{_mode_color(mode_ref[0])}><b>{mode_ref[0]}</b></{_mode_color(mode_ref[0])}> "
            f"| Shift+Tab 切换 | 输入 / 查看命令 "
        ),
    )


def _print_welcome(session_id: str, mode: str):
    mode_line = f"当前权限模式: [{_mode_rich_style(mode)}]{mode}[/{_mode_rich_style(mode)}]（auto=自动执行，approve=需批准，readonly=只读）"
    console.print(
        Panel.fit(
            f"进入 Multi-Agent Orchestrator 对话模式\n"
            f"会话 ID: {session_id}\n"
            f"{mode_line}\n"
            "输入 / 查看命令，输入 /help 查看完整帮助",
            title="MAO Chat",
        )
    )


async def _stream_turn(agent: Agent, user_input: str):
    """流式执行一轮，使用 Rich Live 渲染 Markdown，仿 Claude Code 风格"""
    tool_calls: list[dict[str, Any]] = []
    files_written: list[str] = []
    input_tokens = 0
    output_tokens = 0
    cost_usd = 0.0
    final_content = ""
    is_collaboration = False
    models_used: set[str] = set()
    spinner_task: asyncio.Task | None = None
    spinner_message = ""
    activity_counts: Counter[str] = Counter()
    phase_started: set[str] = set()
    phase_detail_counts: Counter[str] = Counter()
    engineering_run_id = ""
    engineering_status = ""
    engineering_kind = ""
    engineering_risk = ""
    engineering_write_state = ""
    engineering_evidence_count = 0
    engineering_recon_status = ""
    engineering_recon_categories = 0
    engineering_verification_count = 0
    engineering_audit_status = ""
    engineering_audit_gaps: list[str] = []

    def _start_spinner(message: str):
        nonlocal spinner_task, spinner_message
        spinner_message = message
        if spinner_task is not None and not spinner_task.done():
            return

        async def _spin():
            frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
            i = 0
            start = time.monotonic()
            while True:
                elapsed = time.monotonic() - start
                try:
                    live.update(Markdown(f"{spinner_message} {frames[i % len(frames)]} ({elapsed:.1f}s)"))
                except Exception:
                    break
                await asyncio.sleep(0.12)
                i += 1

        spinner_task = asyncio.create_task(_spin())

    def _stop_spinner():
        nonlocal spinner_task
        if spinner_task is not None and not spinner_task.done():
            spinner_task.cancel()
        spinner_task = None

    # 直接用 Markdown 作为 Live 内容，不用 Panel，避免面板边框堆叠
    live = Live(
        Markdown(""),
        console=console,
        refresh_per_second=15,
        vertical_overflow="ellipsis",
        transient=True,
    )
    live.start()
    _start_spinner("🧠 思考中")

    try:
        async for event in agent.run_turn_stream(user_input):
            _stop_spinner()
            if event.type == "delta":
                final_content += event.delta
                # 一旦检测到工具调用，就不再实时展开原始代码块，改为显示执行动画提示
                if agent._has_tool_calls(final_content):
                    _start_spinner("🛠️ 正在调用工具")
                else:
                    live.update(Markdown(final_content))
            elif event.type in ("engineering_start", "engineering_update", "engineering_complete"):
                engineering = event.engineering or {}
                engineering_run_id = str(engineering.get("run_id", engineering_run_id))
                engineering_status = str(engineering.get("status", engineering_status))
                intent = engineering.get("intent", {}) or {}
                policy = intent.get("policy", {}) or {}
                engineering_kind = str(intent.get("kind", engineering_kind))
                engineering_risk = str(intent.get("risk_level", engineering_risk))
                if policy.get("allow_project_writes"):
                    engineering_write_state = (
                        "写入已授权" if intent.get("write_authorized") else "写入需批准"
                    )
                else:
                    engineering_write_state = "只读"
                if "evidence_count" in engineering:
                    engineering_evidence_count = int(engineering.get("evidence_count") or 0)
                reconnaissance = engineering.get("reconnaissance", {}) or {}
                if reconnaissance:
                    engineering_recon_status = str(
                        reconnaissance.get("status", engineering_recon_status)
                    )
                    engineering_recon_categories = len(
                        reconnaissance.get("observed_categories", []) or []
                    )
                if "verification_count" in engineering:
                    engineering_verification_count = int(
                        engineering.get("verification_count") or 0
                    )
                audit = engineering.get("audit") or {}
                if audit:
                    engineering_audit_status = str(
                        audit.get("status", engineering_audit_status)
                    )
                    engineering_audit_gaps = list(dict.fromkeys([
                        *(audit.get("missing_checks") or []),
                        *(audit.get("failed_checks") or []),
                    ]))
                _start_spinner("🧠 思考中")
            elif event.type == "permission_request":
                live.stop()
                req = event.permission_request or {}
                console.print(
                    f"\n[bold yellow]🔒 权限请求：{req.get('message', '')}[/bold yellow]"
                )
                params = req.get("params", {}) or {}
                if req.get("tool") == "collaboration":
                    console.print(f"  子任务数：{params.get('task_count', 0)}")
                    console.print(f"  输出目录：{params.get('output_dir', '')}")
                else:
                    # 通用展示：优先关键字段，兜底显示全部参数
                    shown = False
                    for key, label in (
                        ("path", "路径"),
                        ("command", "命令"),
                        ("url", "URL"),
                        ("query", "查询"),
                    ):
                        value = params.get(key)
                        if value:
                            if key == "path" and req.get("tool") == "write_file":
                                content_len = len(params.get("content", "") or "")
                                console.print(f"  {label}：{value}（约 {content_len} 字符）")
                            else:
                                console.print(f"  {label}：{value}")
                            shown = True
                    if not shown and params:
                        console.print(
                            "  参数："
                            + ", ".join(f"{k}={v}" for k, v in params.items())
                        )
                answer = await asyncio.to_thread(
                    console.input, "允许执行？(y/n/auto)："
                )
                answer_clean = answer.strip().lower()
                if answer_clean in ("auto", "always", "a"):
                    _set_mode(session, agent, mode_ref, "auto")
                    store.save(session)
                    approved = True
                    console.print("[bold red]已切换到自动执行模式，并批准当前请求[/bold red]")
                elif answer_clean in ("y", "yes", "是", "允许"):
                    approved = True
                    console.print("[dim]已允许[/dim]")
                else:
                    approved = False
                    console.print("[dim]已拒绝[/dim]")
                agent.respond_to_permission(req.get("request_id", ""), approved)
                live.start()
            elif event.type == "model_failover":
                failover = event.failover or {}
                from_model = failover.get("from_model", "?")
                to_model = failover.get("to_model", "?")
                reason = failover.get("reason", "")
                console.print(
                    f"[bold yellow]⚠ 模型 {from_model} 连接失效（{reason}），已自动切换到 {to_model}[/bold yellow]"
                )
            elif event.type == "tool_start":
                call = event.tool_call or {}
                tool_name = str(call.get("tool", "unknown"))
                params = call.get("params", {}) or {}
                activity_counts[tool_name] += 1
                phase_key, phase_title = _tool_phase(tool_name)
                if phase_key not in phase_started:
                    console.print(f"\n[bold cyan]● {phase_title}[/bold cyan]")
                    phase_started.add(phase_key)
                shown = phase_detail_counts[phase_key]
                if shown < 4:
                    console.print(f"  [dim]└ {_format_tool_action(tool_name, params)}[/dim]")
                elif shown == 4:
                    console.print("  [dim]└ 后续同类操作已折叠，完成后显示统计[/dim]")
                phase_detail_counts[phase_key] += 1
                _start_spinner(_progress_message(activity_counts))
            elif event.type == "tool_complete":
                call = event.tool_call or {}
                if not call.get("success"):
                    action = _format_tool_action(
                        str(call.get("tool", "unknown")), call.get("params", {}) or {}
                    )
                    console.print(f"  [red]× {action}：{call.get('error') or '执行失败'}[/red]")
                _start_spinner(_progress_message(activity_counts))
            elif event.type == "plan":
                is_collaboration = True
                plan = event.plan or {}
                console.print(
                    f"\n[bold magenta]📋 协作计划：{plan.get('summary', '')}[/bold magenta]"
                )
                for task in plan.get("tasks", []):
                    console.print(
                        f"  • [{task.get('type')}] {task.get('title')} → {task.get('assigned_model')}"
                    )
                    if task.get("assigned_model"):
                        models_used.add(task.get("assigned_model"))
            elif event.type == "task_start":
                task = event.task or {}
                console.print(
                    f"[dim]▶ [{task.get('type')}] {task.get('title')} 开始执行[/dim]"
                )
            elif event.type == "task_retry":
                task = event.task or {}
                console.print(
                    f"[yellow]↻ [{task.get('type')}] {task.get('title')} "
                    f"定向重试 {task.get('attempt')}/{task.get('max_attempts')}[/yellow]"
                )
                if task.get("previous_error"):
                    console.print(f"  [dim]{task['previous_error']}[/dim]")
            elif event.type == "task_complete":
                task = event.task or {}
                status = "✅" if task.get("success") else "❌"
                color = "green" if task.get("success") else "red"
                console.print(
                    f"[{color}]{status} [{task.get('type')}] {task.get('title')}[/{color}]"
                )
                if task.get("error"):
                    console.print(f"  [red]错误：{task['error']}[/red]")
                if task.get("files_written"):
                    for f in task["files_written"]:
                        console.print(f"  [dim]📁 {f}[/dim]")
                if task.get("assigned_model"):
                    models_used.add(task.get("assigned_model"))
            elif event.type == "review_complete":
                review = event.review or {}
                passed = review.get("passed", False)
                status_text = "通过" if passed else "未通过"
                color = "green" if passed else "yellow"
                console.print(
                    f"\n[bold {color}]🔍 审查结果：{status_text}[/]"
                )
                for issue in review.get("issues", []):
                    console.print(f"  ⚠ {issue}")
            elif event.type == "done":
                tool_calls = event.tool_calls
                files_written = event.files_written
                input_tokens = event.input_tokens
                output_tokens = event.output_tokens
                cost_usd = event.cost_usd
                final_content = event.assistant_message
    finally:
        live.stop()

    # Live 只承担临时、有界的流式预览；停止后统一打印一次最终正文，
    # 避免长内容超出终端高度时把每个累计帧留在滚动记录中。
    if final_content:
        if tool_calls or is_collaboration:
            console.print(
                Panel(Markdown(final_content), title="结果", border_style="green")
            )
        else:
            console.print(Markdown(final_content))

    if tool_calls:
        summary_text = Text("\n".join(_summarize_tool_activity(tool_calls)))
        console.print(Panel(summary_text, title="本轮工作", border_style="cyan"))

    if files_written:
        file_text = Text("\n".join(f"✓ {f}" for f in files_written))
        console.print(Panel(file_text, title="交付文件", border_style="green"))

    # 模型归属信息
    main_model = agent.gateway.get_main_model() or "unknown"
    if is_collaboration:
        model_line = f"主模型：{main_model}"
        if models_used:
            model_line += f" | 协作模型：{', '.join(sorted(models_used))}"
    else:
        model_line = f"模型：{main_model}"

    console.print(
        f"[dim]{model_line}  |  输入 token: {input_tokens}  输出 token: {output_tokens}  "
        f"成本: ${cost_usd:.6f}[/dim]"
    )
    if engineering_run_id:
        intent_parts = [part for part in (
            engineering_kind,
            engineering_risk,
            engineering_write_state,
        ) if part]
        intent_suffix = f" · {' / '.join(intent_parts)}" if intent_parts else ""
        console.print(
            f"[dim]工程记录：{engineering_run_id} · "
            f"{engineering_status or 'running'}{intent_suffix}[/dim]"
        )
        if engineering_evidence_count or engineering_recon_status:
            recon_labels = {
                "not_started": "未开始",
                "in_progress": "侦察中",
                "partial": "部分覆盖",
                "completed": "已覆盖",
            }
            recon_text = recon_labels.get(
                engineering_recon_status, engineering_recon_status or "未开始"
            )
            console.print(
                f"[dim]证据：{engineering_evidence_count} 条 · "
                f"项目侦察：{recon_text}（{engineering_recon_categories}/6）[/dim]"
            )
        if engineering_audit_status:
            audit_labels = {
                "not_required": "无需工程验证",
                "passed": "已通过",
                "blocked": "未闭环",
                "failed": "运行失败",
            }
            audit_text = audit_labels.get(
                engineering_audit_status, engineering_audit_status
            )
            gap_text = (
                f" · 缺口：{'、'.join(engineering_audit_gaps)}"
                if engineering_audit_gaps
                else ""
            )
            console.print(
                f"[dim]验证门：{engineering_verification_count} 个 · "
                f"完成审计：{audit_text}{gap_text}[/dim]"
            )


def _cmd_new(store: SessionStore, title: str = ""):
    session = store.create(title=title)
    console.print(f"[bold green]已创建新会话：{session.id}[/bold green]")
    return session


def _cmd_load(store: SessionStore, session_id: str):
    try:
        session = store.load(session_id)
        console.print(f"[bold green]已加载会话：{session.id}[/bold green]")
        return session
    except FileNotFoundError:
        console.print(f"[bold red]会话不存在：{session_id}[/bold red]")
        return None


def _cmd_sessions(store: SessionStore):
    sessions = store.list()
    if not sessions:
        console.print("暂无会话")
        return
    console.print("\n[bold]最近会话：[/bold]")
    for s in sessions[:10]:
        console.print(f"  {s.id}  {s.title or '(无标题)'}  模式={s.approval_mode}  更新于 {s.updated_at}")


_RUN_STATUS_LABELS = {
    "running": "进行中",
    "completed": "已完成",
    "failed": "失败",
    "blocked": "受阻",
}
_PLAN_STATUS_LABELS = {
    "pending": "待开始",
    "in_progress": "进行中",
    "completed": "已完成",
    "failed": "失败",
    "blocked": "受阻",
}
_REQUIREMENT_STATUS_LABELS = {
    "unverified": "未验证",
    "satisfied": "已满足",
    "failed": "未通过",
    "waived": "已豁免",
}
_AUDIT_STATUS_LABELS = {
    "not_required": "无需工程验证",
    "passed": "已通过",
    "blocked": "未闭环",
    "failed": "运行失败",
}


def _cmd_runs(session, run_id: str = "") -> None:
    """本地读取本会话 RunJournal，不调用模型、不产生 token。"""
    from src.core.engineering.journal import RunJournalStore

    run_store = RunJournalStore.from_output_dir(session.output_dir)
    if run_id.strip():
        try:
            journal = run_store.load(run_id.strip())
        except (FileNotFoundError, ValueError) as e:
            console.print(f"[bold red]{e}[/bold red]")
            return
        _print_run_detail(journal)
        return

    journals = run_store.list()
    if not journals:
        console.print("本会话暂无工程运行记录")
        return
    console.print("\n[bold]本会话运行记录（最近 10 条）：[/bold]")
    for journal in journals[:10]:
        status = _RUN_STATUS_LABELS.get(journal.status, journal.status)
        console.print(
            f"  {journal.run_id}  [{status}] {journal.started_at}  "
            f"{journal.objective[:40]}"
        )
    console.print(
        "[dim]使用 /runs <run_id> 查看完整工程记录；本命令为本地读取，未调用模型。[/dim]"
    )


def _print_run_detail(journal) -> None:
    """打印单个 RunJournal 的完整工程记录。"""
    status = _RUN_STATUS_LABELS.get(journal.status, journal.status)
    console.print(f"\n[bold]工程记录 {journal.run_id}[/bold]  状态：{status}")
    console.print(f"目标：{journal.objective}")
    intent = journal.intent
    console.print(
        f"分类：{intent.kind}（{intent.classification_source}，置信度 "
        f"{intent.confidence:.2f}）  风险：{intent.risk_level}  "
        f"写入授权：{'是' if intent.write_authorized else '否'}"
    )

    if journal.plan:
        plan = journal.plan
        plan_status = _PLAN_STATUS_LABELS.get(plan.status, plan.status)
        console.print(f"\n[bold]工作计划[/bold]（{plan_status}）：")
        for step in plan.steps:
            step_label = _PLAN_STATUS_LABELS.get(step.status, step.status)
            line = f"  [{step_label}] {step.title}"
            if step.note:
                line += f"  — {step.note}"
            console.print(line)
        for criterion in plan.acceptance_criteria:
            console.print(f"  验收：{criterion}")

    console.print(f"\n[bold]证据[/bold]（{len(journal.evidence)} 条）：")
    for item in journal.evidence[-20:]:
        mark = "✓" if item.success else "✗"
        line = f"  [{item.kind}]{mark} {item.claim}"
        if item.path:
            line += f"（{item.path}）"
        console.print(line)
    if len(journal.evidence) > 20:
        console.print(f"  … 其余 {len(journal.evidence) - 20} 条略")

    console.print(f"\n[bold]验证门[/bold]（{len(journal.verification)} 个）：")
    for gate in journal.verification:
        mark = "✓" if gate.passed else ("✗" if gate.passed is False else "…")
        console.print(f"  {mark} [{gate.check_type}] {gate.command_or_check}")

    if journal.requirements:
        console.print(f"\n[bold]需求核对[/bold]（{len(journal.requirements)} 项）：")
        for req in journal.requirements:
            label = _REQUIREMENT_STATUS_LABELS.get(req.status, req.status)
            console.print(f"  [{label}] {req.requirement}")

    if journal.audit:
        audit = journal.audit
        label = _AUDIT_STATUS_LABELS.get(audit.status, audit.status)
        console.print(f"\n[bold]完成审计[/bold]：{label}")
        if audit.missing_checks:
            console.print(f"  缺失检查：{'、'.join(audit.missing_checks)}")
        if audit.failed_checks:
            console.print(f"  失败检查：{'、'.join(audit.failed_checks)}")
        if audit.summary:
            console.print(f"  摘要：{audit.summary}")

    if journal.decisions:
        console.print(f"\n[bold]决策[/bold]（{len(journal.decisions)} 条）：")
        for decision in journal.decisions:
            console.print(f"  - {decision}")
    if journal.files_changed:
        console.print(f"\n[bold]修改文件[/bold]（{len(journal.files_changed)} 个）：")
        for path in journal.files_changed:
            console.print(f"  - {path}")
    if journal.residual_risks:
        console.print(f"\n[bold]残余风险[/bold]：")
        for risk in journal.residual_risks:
            console.print(f"  - {risk}")
    if journal.metrics:
        console.print("\n[bold]指标[/bold]：")
        for key, value in journal.metrics.items():
            console.print(f"  {key} = {value}")


def _parse_tree_args(raw: str) -> tuple[str, int]:
    """解析 `/tree [路径] [深度]`，保留 Windows 路径中的空格和反斜杠。"""
    value = raw.strip()
    if not value:
        return ".", 4
    parts = value.rsplit(maxsplit=1)
    if len(parts) == 2 and parts[1].isdigit():
        return parts[0], int(parts[1])
    return value, 4


def _cmd_tree(raw: str) -> bool:
    """本地生成项目树，不调用 Gateway，也不产生 token。"""
    from src.tools.search_tools import project_tree

    path, max_depth = _parse_tree_args(raw)
    result = project_tree(path=path, max_depth=max_depth)
    if not result.success:
        console.print(f"[bold red]项目树生成失败：{result.error}[/bold red]")
        return False
    console.print(Panel(result.output, title="项目结构", border_style="cyan"))
    console.print("[dim]本命令在本地执行，未调用模型，未产生 token。[/dim]")
    return True


def _cmd_memory_add(store: MemoryStore, category: str, content: str, tags: list[str] | None = None):
    """手动添加长期记忆"""
    from src.core.memory import MemoryEntry

    try:
        entry = MemoryEntry(category=category, content=content, tags=tags or [], source="user")
        store.add(entry)
        console.print(f"[bold green]已添加记忆：[/bold green] {entry.id} [{entry.category}]")
    except Exception as e:
        console.print(f"[bold red]添加记忆失败：{e}[/bold red]")


def _cmd_memory_list(store: MemoryStore, category: str | None = None):
    """列出长期记忆"""
    entries = store.list(category=category)
    if not entries:
        console.print("暂无记忆")
        return
    console.print(f"\n[bold]记忆列表（共 {len(entries)} 条）：[/bold]")
    for entry in entries:
        console.print(f"  {entry.id} [{entry.category}] {entry.content[:60]}")


def _cmd_memory_search(store: MemoryStore, query: str):
    """搜索长期记忆"""
    entries = store.search(query, top_k=10)
    if not entries:
        console.print("未找到相关记忆")
        return
    console.print(f"\n[bold]搜索结果（top {len(entries)}）：[/bold]")
    for entry in entries:
        console.print(f"  {entry.id} [{entry.category}] {entry.content[:80]}")


def _cmd_memory_forget(store: MemoryStore, entry_id: str):
    """删除指定记忆"""
    if store.delete(entry_id):
        console.print(f"[bold green]已删除记忆：{entry_id}[/bold green]")
    else:
        console.print(f"[bold red]记忆不存在：{entry_id}[/bold red]")


def _cmd_memory_index(store: MemoryStore):
    """重建项目文件索引"""
    from src.core.memory import ProjectIndexer

    try:
        indexer = ProjectIndexer(store)
        stats = indexer.index_project(root_dir=".", force=True)
        console.print(
            f"[bold green]索引完成：[/bold green] 扫描 {stats.get('scanned', 0)} 个文件，"
            f"新增 {stats.get('added', 0)} 个，更新 {stats.get('updated', 0)} 个，"
            f"总计 {stats.get('total', 0)} 个"
        )
    except Exception as e:
        console.print(f"[bold red]索引失败：{e}[/bold red]")


def _cmd_memory_summarize(gateway: GatewayClient, store: MemoryStore, session: Any):
    """总结当前会话并保存到长期记忆"""
    from src.core.summarizer import SessionSummarizer

    try:
        summarizer = SessionSummarizer(gateway, store)
        ids = summarizer.summarize(session, source=f"session:{session.id}")
        if ids:
            console.print(f"[bold green]已总结并保存 {len(ids)} 条记忆[/bold green]")
            for entry_id in ids:
                console.print(f"  ✓ {entry_id}")
        else:
            console.print("[dim]未提取到可保存的记忆[/dim]")
    except Exception as e:
        console.print(f"[bold red]总结失败：{e}[/bold red]")


def _cmd_plan(gateway: GatewayClient, request: str, output_dir: str, approval_mode: str = "auto"):
    """复用现有 Orchestrator + Dispatcher 执行一次性任务"""
    from src.core.dispatcher import Dispatcher
    from src.core.orchestrator import Orchestrator
    from src.core.worker import Worker, load_workers_config

    if approval_mode == "readonly":
        console.print("[bold yellow]只读模式：/plan 已跳过（不会执行任何写文件操作）[/bold yellow]")
        return

    console.print("\n[bold cyan]🧠 Orchestrator 正在规划...[/bold cyan]")
    orchestrator = Orchestrator(gateway)
    plan = orchestrator.plan(request)

    console.print(f"[bold green]📋 拆分为 {len(plan.tasks)} 个子任务[/bold green]")
    for task in plan.tasks:
        console.print(f"  • [{task.type}] {task.title} → {task.assigned_model}")

    if approval_mode == "approve":
        console.print(
            f"\n[bold yellow]🔒 即将执行 {len(plan.tasks)} 个子任务并自动写入文件到 {output_dir}[/bold yellow]"
        )
        answer = console.input("允许执行？(y/n)：")
        if answer.strip().lower() not in ("y", "yes", "是", "允许"):
            console.print("[dim]已取消[/dim]")
            return

    workers_config = load_workers_config()
    worker = Worker(gateway, workers_config)
    dispatcher = Dispatcher(worker)
    results = dispatcher.dispatch(plan, output_dir=output_dir)

    console.print("\n[bold green]📁 输出文件：[/bold green]")
    for result in results:
        if result.success:
            for f in result.files_written:
                console.print(f"  ✓ {f}")


def _cmd_test_models(gateway: GatewayClient):
    """诊断所有已配置模型的连通性并更新进程内健康状态。"""
    console.print("[bold]🔍 正在测试所有模型连通性...[/bold]")
    console.print("[dim]每个模型会发送一个最小请求，可能产生少量 token 消耗。[/dim]")
    for model_name in gateway.models:
        result = gateway.test_model(model_name)
        detail = result.get("error", "") if not result.get("success") else f"{result.get('response_time_ms', 0):.0f}ms"
        line = Text(f"  {model_name}: ")
        if result.get("success"):
            line.append("✅ 正常", style="green")
        else:
            line.append("❌ 失败", style="red")
        if detail:
            line.append(f" {detail}")
        console.print(line)
    console.print("[dim]可恢复的失败模型会进入健康冷却；认证或配置错误不会自动切换。[/dim]")


def _cmd_tools():
    from src.tools.registry import tool_registry

    console.print("[bold]可用工具：[/bold]")
    for name in tool_registry.list_tools():
        spec = tool_registry.get(name)
        if spec is None:
            continue
        params_str = ", ".join(spec.params.keys()) if spec.params else ""
        suffix = f"({params_str})" if params_str else ""
        console.print(f"  • [cyan]{name}{suffix}[/cyan] - {spec.description}")
    console.print(
        "\n调用格式：```tool:<工具名>\\n{JSON 参数}\\n```"
    )


def _set_mode(session, agent, mode_ref: list[str], mode: str) -> bool:
    """设置会话权限模式"""
    if mode not in MODES:
        console.print(f"[bold red]未知模式：{mode}，可选：{' / '.join(MODES)}[/bold red]")
        return False
    session.approval_mode = mode  # type: ignore[assignment]
    agent.approval_mode = mode  # type: ignore[assignment]
    mode_ref[0] = mode
    style = _mode_rich_style(mode)
    console.print(f"[{style}]已切换权限模式：{mode}[/{style}]")
    return True


def _cmd_context(agent: Agent) -> dict[str, Any]:
    """显示本地运行时上下文状态，不调用模型、不消耗 token。"""
    status = agent.get_context_status()
    max_tokens = status.get("input_budget_tokens", status["max_context_tokens"])
    current_tokens = status["current_tokens"]
    usage = (current_tokens / max_tokens * 100) if max_tokens > 0 else 0.0
    source = status.get(
        "context_window_source",
        "model_config" if status.get("max_context_source") == "model_config" else "unverified_default",
    )
    compaction = "已启用" if status["compaction_enabled"] else "未启用"
    lines = [
        f"当前模型：{status['model_alias']}",
        f"Provider：{status['provider']}",
        f"上游请求模型：{status['model_id']}",
        f"上游硬窗口：{status.get('context_window_tokens', 0):,} tokens" if status.get("context_window_tokens") else "上游硬窗口：未知",
        f"MAO 安全输入预算：{current_tokens:,} / {max_tokens:,} tokens（{usage:.1f}%）",
        f"输出预留：{status.get('output_reserve_tokens', 0):,} tokens",
        f"当前可用：{status.get('remaining_input_tokens', max_tokens - current_tokens):,} tokens",
        f"预算来源：{source}",
        (
            f"自动压缩：{compaction}，约 {status['compaction_limit_tokens']:,} tokens "
            f"触发（{status['compaction_threshold']:.0%}）"
        ),
        "说明：anthropic 表示兼容协议，不代表模型是 Claude。",
    ]
    lines.extend(f"警告：{warning}" for warning in status.get("warnings", []))
    console.print(Panel(Text("\n".join(lines)), title="上下文状态", border_style="cyan"))
    return status


def run_chat_loop(
    gateway: GatewayClient,
    store: SessionStore,
    session_id: str | None = None,
) -> None:
    """进入交互式对话 REPL"""
    if session_id:
        session = _cmd_load(store, session_id)
        if session is None:
            return
    else:
        session = _cmd_new(store)

    mode_ref = [session.approval_mode]
    pt_session = _make_prompt_session(mode_ref)
    memory_store = MemoryStore()
    # 加载扩展（Hooks + MCP 工具源），幂等
    from src.tools.extensions import load_extensions

    extension_status = load_extensions()
    diagnostics = extension_status["diagnostics"]
    if diagnostics:
        console.print(
            Text(
                f"扩展加载完成，但发现 {len(diagnostics)} 个配置问题；核心功能可继续使用。",
                style="yellow",
            )
        )
        for diagnostic in diagnostics[:3]:
            location = diagnostic.get("config_path", "扩展配置")
            entry = diagnostic.get("entry")
            if entry:
                location = f"{location} {entry}"
            console.print(
                Text(
                    f"  - {location}: {diagnostic['message']}；{diagnostic['action']}",
                    style="dim",
                )
            )
        if len(diagnostics) > 3:
            console.print(Text("  - 其余问题请在 Web 扩展诊断接口中查看。", style="dim"))
    agent = Agent(gateway, session, memory_store=memory_store)

    _print_welcome(session.id, mode_ref[0])

    try:
        while True:
            try:
                user_input = pt_session.prompt(
                    HTML(f"\n<b>[<{_mode_color(mode_ref[0])}>{mode_ref[0]}</{_mode_color(mode_ref[0])}>] &gt;</b> ")
                ).strip()
            except (EOFError, KeyboardInterrupt):
                console.print("\n退出对话。")
                break

            if not user_input:
                continue

            # 同步 agent 与 session 的模式（可能通过 Shift+Tab 切换）
            if agent.approval_mode != mode_ref[0]:
                _set_mode(session, agent, mode_ref, mode_ref[0])

            if user_input.startswith("/"):
                parts = user_input.split(" ", 1)
                cmd = parts[0].lower()
                arg = parts[1] if len(parts) > 1 else ""

                if cmd in ("/exit", "/quit"):
                    break
                elif cmd == "/new":
                    store.save(session)
                    session = _cmd_new(store, title=arg)
                    mode_ref[0] = session.approval_mode
                    pt_session = _make_prompt_session(mode_ref)
                    agent = Agent(gateway, session, memory_store=memory_store)
                elif cmd == "/load":
                    if not arg:
                        console.print("[bold red]用法：/load <session_id>[/bold red]")
                        continue
                    store.save(session)
                    loaded = _cmd_load(store, arg)
                    if loaded:
                        session = loaded
                        mode_ref[0] = session.approval_mode
                        pt_session = _make_prompt_session(mode_ref)
                        agent = Agent(gateway, session, memory_store=memory_store)
                elif cmd == "/save":
                    store.save(session)
                    console.print(f"[bold green]已保存会话：{session.id}[/bold green]")
                elif cmd == "/sessions":
                    _cmd_sessions(store)
                elif cmd == "/runs":
                    _cmd_runs(session, arg)
                elif cmd == "/context":
                    _cmd_context(agent)
                elif cmd == "/tree":
                    _cmd_tree(arg)
                elif cmd == "/plan":
                    if not arg:
                        console.print("[bold red]用法：/plan <需求>[/bold red]")
                        continue
                    _cmd_plan(gateway, arg, session.output_dir, mode_ref[0])
                elif cmd == "/memory":
                    mem_parts = arg.split(" ", 1)
                    subcmd = mem_parts[0].strip().lower() if mem_parts else ""
                    subarg = mem_parts[1] if len(mem_parts) > 1 else ""
                    if subcmd == "add":
                        add_parts = subarg.split(" ", 1)
                        if len(add_parts) < 2:
                            console.print("[bold red]用法：/memory add <分类> <内容>[/bold red]")
                            continue
                        _cmd_memory_add(memory_store, add_parts[0].strip(), add_parts[1].strip())
                    elif subcmd == "list":
                        _cmd_memory_list(memory_store, subarg.strip() or None)
                    elif subcmd == "search":
                        if not subarg.strip():
                            console.print("[bold red]用法：/memory search <查询>[/bold red]")
                            continue
                        _cmd_memory_search(memory_store, subarg.strip())
                    elif subcmd == "forget":
                        if not subarg.strip():
                            console.print("[bold red]用法：/memory forget <id>[/bold red]")
                            continue
                        _cmd_memory_forget(memory_store, subarg.strip())
                    elif subcmd == "index":
                        _cmd_memory_index(memory_store)
                    elif subcmd == "summarize":
                        _cmd_memory_summarize(gateway, memory_store, session)
                    else:
                        console.print(
                            "[bold red]未知 /memory 子命令，可用：add/list/search/forget/index/summarize[/bold red]"
                        )
                elif cmd == "/mode":
                    if not arg:
                        # 无参数时循环切换：approve -> auto -> readonly -> approve
                        idx = MODES.index(mode_ref[0])
                        next_mode = MODES[(idx + 1) % len(MODES)]
                        if _set_mode(session, agent, mode_ref, next_mode):
                            store.save(session)
                        continue
                    if _set_mode(session, agent, mode_ref, arg.strip()):
                        store.save(session)
                elif cmd == "/auto":
                    if _set_mode(session, agent, mode_ref, "auto"):
                        store.save(session)
                elif cmd == "/approve":
                    if _set_mode(session, agent, mode_ref, "approve"):
                        store.save(session)
                elif cmd == "/readonly":
                    if _set_mode(session, agent, mode_ref, "readonly"):
                        store.save(session)
                elif cmd == "/tools":
                    _cmd_tools()
                elif cmd == "/test-models":
                    _cmd_test_models(gateway)
                elif cmd == "/help":
                    console.print(COMMANDS)
                else:
                    console.print(f"[bold red]未知命令：{cmd}，输入 /help 查看帮助[/bold red]")
                continue

            try:
                asyncio.run(_stream_turn(agent, user_input))
                store.save(session)
            except Exception as e:
                console.print(Text(f"错误：{e}", style="bold red"))

    finally:
        from src.tools.extensions import shutdown_extensions

        shutdown_extensions()
        store.save(session)
        console.print(f"\n[bold]会话已保存：{session.id}[/bold]")
        gateway.print_billing()
