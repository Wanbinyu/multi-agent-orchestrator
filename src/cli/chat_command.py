"""CLI 交互式对话命令"""
from __future__ import annotations

import asyncio
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.shortcuts import CompleteStyle
from prompt_toolkit.styles import Style
from rich.console import Console, Group
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

from src.core.agent import Agent
from src.core.engineering import SessionRecoveryManager
from src.core.memory import MemoryStore
from src.core.session import SessionStore
from src.gateway.client import GatewayClient


console = Console()


SLASH_COMMANDS: list[tuple[str, str, str]] = [
    ("/new", "/new [标题]", "创建新会话"),
    ("/load", "/load <id>", "加载已有会话"),
    ("/resume", "/resume <continue|abandon>", "确认继续或放弃中断任务"),
    ("/save", "/save", "保存当前会话"),
    ("/sessions", "/sessions", "列出最近会话"),
    ("/runs", "/runs [run_id]", "本地查看本会话工程运行记录"),
    ("/report", "/report [session|today]", "本地汇总真实交付与 token 指标"),
    ("/context", "/context", "显示上下文预算与自动压缩状态"),
    ("/status", "/status", "显示权限、模型、深度、协作、token 与最近验证"),
    ("/checkpoint", "/checkpoint [create|list|preview|restore|auto|prune]", "工作区检查点（与用户 Git 分离）"),
    ("/tree", "/tree [路径] [深度]", "零 token 显示项目结构"),
    ("/plan", "/plan <需求>", "执行一次性多模型任务计划"),
    ("/plan enter", "/plan enter [目标]", "进入持久化只读 Plan 模式"),
    ("/plan show", "/plan show", "查看当前方案"),
    ("/plan revise", "/plan revise <意见>", "要求修订当前方案"),
    ("/plan approve", "/plan approve", "批准方案并开始实施"),
    ("/plan cancel", "/plan cancel", "取消 Plan 模式"),
    ("/memory add", "/memory add <分类> <内容>", "添加长期记忆"),
    ("/memory list", "/memory list [分类]", "列出长期记忆"),
    ("/memory search", "/memory search <查询>", "搜索长期记忆"),
    ("/memory forget", "/memory forget <id>", "删除长期记忆"),
    ("/memory index", "/memory index", "重建项目文件索引"),
    ("/memory summarize", "/memory summarize", "总结当前会话并保存到记忆"),
    ("/mode", "/mode <auto|approve|readonly>", "切换权限模式"),
    ("/depth", "/depth <auto|fast|standard|deep>", "设置执行深度"),
    ("/collab", "/collab <auto|single|multi>", "设置多模型协作：默认单 Agent"),
    ("/routing", "/routing <auto|fixed>", "设置模型路由"),
    ("/adversarial", "/adversarial <on|off>", "切换实验对抗测试"),
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
        "  - Shift+Tab 切换权限模式（当前模式看屏幕底部工具栏，不在行首）",
        "  - 权限询问时输入 auto/always 可切换到自动模式并批准当前请求",
        "  - 默认单 Agent。/collab multi 才强制多模型；auto 仅 deep 的修改/构建会协作",
        "  - /status 查看当前会话；中断后用 /resume continue|abandon，确认前不执行工具",
        "  - Ctrl+C 中断本轮；Journal 不会停在 running",
        "  - 首次写入前默认自动快照；/checkpoint auto off 可关闭；恢复仍需 preview + confirm",
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
DEPTHS = ["auto", "fast", "standard", "deep"]
COLLAB_MODES = ["auto", "single", "multi"]
ROUTING_MODES = ["auto", "fixed"]


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
    "git_diff": ("explore", "探索项目"),
    "git_log": ("explore", "探索项目"),
    "git_commit": ("change", "生成交付物"),
    "edit_file": ("change", "生成交付物"),
    "discover_project_commands": ("execute", "执行验证"),
    "list_dir": ("explore", "探索项目"),
    "glob_files": ("explore", "探索项目"),
    "read_file": ("explore", "探索项目"),
    "grep_content": ("search", "检索代码"),
    "search_project_files": ("search", "检索代码"),
    "repo_map": ("search", "检索代码"),
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
        "git_diff": "查看 Git diff",
        "git_log": "查看 Git 提交",
        "git_commit": "提交 Git 变更",
        "edit_file": "编辑文件",
        "discover_project_commands": "发现项目命令",
        "glob_files": "匹配文件",
        "read_file": "读取文件",
        "grep_content": "搜索内容",
        "search_project_files": "搜索项目",
        "repo_map": "仓库导航",
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


# 底部栏：无反白底，普通亮字（Windows/多数终端）
_CLI_PROMPT_STYLE = Style.from_dict(
    {
        "bottom-toolbar": "noreverse bg:default #e8e8e8",
        "bottom-toolbar.text": "noreverse bg:default #e8e8e8",
    }
)

# 欢迎区小猫：下巴+双爪搭台沿
_MAO_MASCOT = """\
           /\\_/\\
          ( ° ° )
     ══o══(  ω  )══o══"""


def _format_usage_toolbar(usage: dict[str, Any] | None) -> str:
    """底部工具栏里的 token / 成本摘要。"""
    if not usage:
        return "token: —"
    last_in = int(usage.get("last_in", 0) or 0)
    last_out = int(usage.get("last_out", 0) or 0)
    total_in = int(usage.get("total_in", 0) or 0)
    total_out = int(usage.get("total_out", 0) or 0)
    total_cost = float(usage.get("total_cost", 0.0) or 0.0)
    # 效率：本轮输出/输入，>1 表示答比问长
    if last_in > 0:
        eff = last_out / last_in
        eff_s = f"效率 {eff:.2f}x"
    else:
        eff_s = "效率 —"
    return (
        f"本轮 ↑{last_in} ↓{last_out} | 会话 ↑{total_in} ↓{total_out} "
        f"| ${total_cost:.4f} | {eff_s}"
    )


def _make_prompt_session(
    mode_ref: list[str],
    *,
    on_mode_change: Any | None = None,
    usage_ref: dict[str, Any] | None = None,
) -> PromptSession:
    """创建支持 Shift+Tab 切换模式的 prompt_toolkit 会话。

    模式与 token 用量显示在底部工具栏（实时刷新），行首仅 ``>``。
    底部栏使用 noreverse，避免默认白底黑字。
    """
    kb = KeyBindings()

    @kb.add(Keys.BackTab)
    def _switch_mode(event):
        idx = MODES.index(mode_ref[0]) if mode_ref[0] in MODES else 0
        mode_ref[0] = MODES[(idx + 1) % len(MODES)]
        if on_mode_change is not None:
            try:
                on_mode_change(mode_ref[0])
            except Exception:
                pass
        event.app.invalidate()

    def _toolbar() -> HTML:
        mode = mode_ref[0] if mode_ref else "approve"
        usage_text = _format_usage_toolbar(usage_ref)
        return HTML(
            f" 权限:<{_mode_color(mode)}><b>{mode}</b></{_mode_color(mode)}> "
            f"| {usage_text} "
            f"| Shift+Tab 或 a/p/r | / 命令 "
        )

    return PromptSession(
        key_bindings=kb,
        completer=SlashCommandCompleter(),
        complete_while_typing=True,
        complete_style=CompleteStyle.COLUMN,
        bottom_toolbar=_toolbar,
        style=_CLI_PROMPT_STYLE,
    )


def _prompt_message() -> HTML:
    """固定简洁提示符；当前模式与 token 见底部工具栏。"""
    return HTML("\n<b>&gt;</b> ")


async def _read_permission_response(mode_ref: list[str], on_mode_change: Any) -> str:
    """Read a decision while keeping Shift+Tab available."""
    kb = KeyBindings()

    def _set_mode(mode: str, event: Any | None = None) -> None:
        mode_ref[0] = mode
        try:
            on_mode_change(mode)
        except Exception:
            pass
        if event is not None:
            event.app.invalidate()

    @kb.add(Keys.BackTab)
    def _switch_mode(event):
        index = MODES.index(mode_ref[0]) if mode_ref[0] in MODES else 0
        mode = MODES[(index + 1) % len(MODES)]
        _set_mode(mode, event)
        if mode == "auto":
            event.app.exit(result="auto")
        elif mode == "readonly":
            event.app.exit(result="no")

    @kb.add("y")
    def _approve(event):
        event.app.exit(result="yes")

    @kb.add("n")
    def _deny(event):
        event.app.exit(result="no")

    @kb.add("a")
    def _auto(event):
        _set_mode("auto", event)
        event.app.exit(result="auto")

    @kb.add("p")
    def _approve_mode(event):
        _set_mode("approve", event)

    @kb.add("r")
    def _readonly(event):
        _set_mode("readonly", event)
        event.app.exit(result="no")

    @kb.add(Keys.Enter)
    def _submit(event):
        value = event.app.current_buffer.text.strip().casefold()
        if value in {"y", "yes", "允许", "是", "是的", "同意", "好"}:
            event.app.exit(result="yes")
        elif value in {"auto", "always"}:
            _set_mode("auto", event)
            event.app.exit(result="auto")
        else:
            event.app.exit(result="no")

    def _toolbar() -> HTML:
        mode = mode_ref[0] if mode_ref else "approve"
        return HTML(
            f" 权限:<{_mode_color(mode)}><b>{mode}</b></{_mode_color(mode)}> "
            "| y=允许 n=拒绝 | Shift+Tab=切换模式"
        )

    prompt = PromptSession(
        key_bindings=kb,
        bottom_toolbar=_toolbar,
        style=_CLI_PROMPT_STYLE,
    )
    try:
        answer = await prompt.prompt_async("允许执行？ ")
    except (EOFError, KeyboardInterrupt):
        return "no"
    return (answer or "").strip().casefold() or "no"


def _print_welcome(session_id: str, mode: str):
    mode_line = (
        f"当前权限: [{_mode_rich_style(mode)}]{mode}[/{_mode_rich_style(mode)}] "
        f"（auto=自动 · approve=需批准 · readonly=只读）"
    )
    body = (
        f"[cyan]{_MAO_MASCOT}[/cyan]\n\n"
        f"[bold]MAO Chat[/bold]  ·  多模型工程对话\n"
        f"会话: [dim]{session_id}[/dim]\n"
        f"{mode_line}\n"
        f"[dim]底部栏显示权限与 token 用量 · Shift+Tab 切换模式 · 输入 / 看命令[/dim]"
    )
    console.print(Panel.fit(body, title="你好", border_style="cyan"))


async def _stream_turn(
    agent: Agent,
    user_input: str,
    *,
    mode_ref: list[str] | None = None,
    session: Any | None = None,
    store: SessionStore | None = None,
) -> dict[str, Any]:
    """流式执行一轮，使用 Rich Live 渲染 Markdown，仿 Claude Code 风格。

    返回本轮 token/成本摘要，供底部工具栏刷新。
    执行中可通过热键 a/p/r 切换权限模式（无需等到提示符）。
    """
    sess = session if session is not None else getattr(agent, "session", None)

    def _apply_mode_hotkey(mode: str) -> None:
        if mode_ref is not None and mode_ref:
            mode_ref[0] = mode
        if sess is not None:
            sess.approval_mode = mode  # type: ignore[assignment]
        agent.approval_mode = mode  # type: ignore[assignment]
        if store is not None and sess is not None:
            try:
                store.save(sess)
            except Exception:
                pass

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
    worker_previews: dict[str, str] = {}
    worker_statuses: dict[str, dict[str, Any]] = {}
    plan_total = 0
    completed_task_ids: set[str] = set()
    current_task_id = ""
    last_progress_detail = ""
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
    engineering_routed_model = ""
    engineering_routing_source = ""
    engineering_routing_reason = ""
    turn_started_at = time.monotonic()

    def _collaboration_progress_message() -> str:
        if not plan_total:
            return last_progress_detail or "协作执行"
        task = worker_statuses.get(current_task_id, {})
        title = task.get("title") or current_task_id or "等待调度"
        model = task.get("model") or task.get("assigned_model") or "未知模型"
        iteration = task.get("iteration")
        maximum = task.get("max_iterations")
        iteration_text = (
            f" | 工具轮 {iteration}/{maximum}"
            if iteration is not None and maximum
            else ""
        )
        detail = last_progress_detail or task.get("phase") or "等待事件"
        return (
            f"协作进度 {len(completed_task_ids)}/{plan_total} | 当前任务：{title} "
            f"| 模型：{model}{iteration_text} | 最近动作：{detail}"
        )

    def _start_spinner(message: str):
        nonlocal spinner_task, spinner_message
        spinner_message = message
        if spinner_task is not None and not spinner_task.done():
            return

        async def _spin():
            from src.cli.hotkeys import apply_hotkey_if_any

            frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
            i = 0
            while True:
                # 任务进行中可按 a/p/r 切换权限（无需回车），对齐常见 CLI Agent 体验
                apply_hotkey_if_any(
                    mode_ref=mode_ref,
                    on_mode_change=_apply_mode_hotkey,
                    announce=lambda m: console.print(
                        f"[bold cyan]（热键）已切换权限模式：{m}[/bold cyan]"
                    ),
                )
                elapsed = time.monotonic() - turn_started_at
                try:
                    # 明确是「已用秒数」，不是进度百分比
                    live.update(
                        Markdown(
                            f"{spinner_message} {frames[i % len(frames)]} "
                            f"已用时 {elapsed:.1f}s "
                            f"| 热键 a=auto p=approve r=readonly | Ctrl+C 中断"
                        )
                    )
                except Exception:
                    break
                await asyncio.sleep(0.12)
                i += 1

        spinner_task = asyncio.create_task(_spin())

    def _set_spinner_message(message: str) -> None:
        if message:
            _start_spinner(message)

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
            if event.type == "delta":
                final_content += event.delta
                # 一旦检测到工具调用，就不再实时展开原始代码块，改为显示执行动画提示
                if agent._has_tool_calls(final_content):
                    _set_spinner_message("🛠️ 正在调用工具")
                else:
                    live.update(Markdown(final_content))
            elif event.type in ("engineering_start", "engineering_update", "engineering_complete"):
                engineering = event.engineering or {}
                engineering_run_id = str(engineering.get("run_id", engineering_run_id))
                engineering_status = str(engineering.get("status", engineering_status))
                intent = engineering.get("intent", {}) or {}
                effective_intent = engineering.get("effective_intent", {}) or {}
                display_intent = effective_intent or intent
                policy = intent.get("policy", {}) or display_intent.get("policy", {}) or {}
                engineering_kind = str(display_intent.get("kind", engineering_kind))
                engineering_risk = str(display_intent.get("risk_level", engineering_risk))
                if effective_intent.get("write_authorized"):
                    engineering_write_state = "写入已授权"
                elif getattr(agent, "approval_mode", "approve") == "readonly":
                    engineering_write_state = "只读"
                elif policy.get("allow_project_writes") or policy.get(
                    "permission_follows_session"
                ):
                    engineering_write_state = (
                        "写入已授权"
                        if (intent or display_intent).get("write_authorized")
                        else "写入需批准"
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
                routing = engineering.get("model_routing") or {}
                if routing:
                    engineering_routed_model = str(
                        routing.get("selected_model", engineering_routed_model)
                    )
                    engineering_routing_source = str(
                        routing.get("source", engineering_routing_source)
                    )
                    engineering_routing_reason = str(
                        routing.get("reason", engineering_routing_reason)
                    )
                _set_spinner_message("🧠 思考中")
            elif event.type == "permission_request":
                live.stop()
                _stop_spinner()
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
                console.print(
                    "[dim]y=允许，n=拒绝，Shift+Tab 在 auto/approve/readonly 间切换。"
                    "auto 只自动批准会话默认请求；deny、显式 ask 和复杂 shell 安全规则仍生效。[/dim]"
                )
                current_mode = getattr(agent, "approval_mode", "approve")
                decision = req.get("decision") or {}
                auto_can_approve = (
                    req.get("tool") == "collaboration"
                    or decision.get("source", "session") == "session"
                )
                if current_mode == "auto" and auto_can_approve:
                    answer = "auto"
                else:
                    answer = await _read_permission_response(
                        mode_ref or [current_mode], _apply_mode_hotkey
                    )
                answer_clean = answer.strip().lower()
                if answer_clean in ("auto", "always", "a"):
                    _apply_mode_hotkey("auto")
                    approved = True
                    console.print(
                        "[bold red]已切换到自动执行模式，并批准当前请求；"
                        "本会话后续非只读工具默认不再询问（deny 规则仍生效）[/bold red]"
                    )
                elif answer_clean in ("y", "yes", "是", "是的", "同意", "好", "允许"):
                    approved = True
                    console.print("[dim]已允许[/dim]")
                else:
                    approved = False
                    console.print("[dim]已拒绝[/dim]")
                agent.respond_to_permission(req.get("request_id", ""), approved)
                live.start()
                _start_spinner("等待后续事件")
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
                _set_spinner_message(_progress_message(activity_counts))
            elif event.type == "tool_complete":
                call = event.tool_call or {}
                if not call.get("success"):
                    action = _format_tool_action(
                        str(call.get("tool", "unknown")), call.get("params", {}) or {}
                    )
                    console.print(f"  [red]× {action}：{call.get('error') or '执行失败'}[/red]")
                _set_spinner_message(_progress_message(activity_counts))
            elif event.type == "plan":
                is_collaboration = True
                plan = event.plan or {}
                plan_total = len(plan.get("tasks", []))
                console.print(
                    f"\n[bold magenta]📋 协作计划：{plan.get('summary', '')}[/bold magenta]"
                )
                for task in plan.get("tasks", []):
                    console.print(
                        f"  • [{task.get('type')}] {task.get('title')} → {task.get('assigned_model')}"
                    )
                    if task.get("assigned_model"):
                        models_used.add(task.get("assigned_model"))
            elif event.type == "worker_status":
                task = event.task or {}
                task_id = str(task.get("id", ""))
                if task_id:
                    worker_statuses[task_id] = task
                    current_task_id = task_id
                    last_progress_detail = str(
                        task.get("phase") or task.get("status") or "worker"
                    )
                delta = str(task.get("delta", "") or "")
                if task_id and delta:
                    worker_previews[task_id] = (
                        worker_previews.get(task_id, "") + delta
                    )[-6000:]
                title = task.get("title") or task_id or "协作任务"
                model = task.get("model") or task.get("assigned_model") or "未知模型"
                phase = task.get("phase") or "worker"
                status = task.get("status") or "进行中"
                preview = worker_previews.get(task_id, "")
                if preview:
                    preview = f"\n\n{preview}"
                live.update(Markdown(
                    f"**协作任务：{title}**\n\n"
                    f"模型：`{model}` · 阶段：`{phase}` · 状态：`{status}`"
                    f"{preview}"
                ))
                _set_spinner_message(_collaboration_progress_message())
            elif event.type == "task_heartbeat":
                heartbeat = event.task or {}
                active = heartbeat.get("active_tasks") or []
                active_text = "、".join(
                    str(item.get("title") or item.get("id") or "未知任务")
                    for item in active
                ) or "调度中"
                idle = float(heartbeat.get("idle_seconds") or 0)
                if active:
                    current_task_id = str(active[-1].get("id") or current_task_id)
                    for item in active:
                        if item.get("id"):
                            worker_statuses[str(item["id"])] = item
                    last_progress_detail = "任务运行中"
                else:
                    last_progress_detail = f"等待事件（最近 {idle:.1f}s）"
                warning = "⚠ " if idle >= 15 else ""
                live.update(Markdown(
                    f"{warning}**协作仍在运行**\n\n"
                    f"活动任务：{active_text}\n\n"
                    f"已运行 {float(heartbeat.get('elapsed_seconds') or 0):.1f}s，"
                    f"最近事件距今 {idle:.1f}s"
                ))
                _set_spinner_message(_collaboration_progress_message())
            elif event.type == "task_start":
                task = event.task or {}
                if task.get("id"):
                    current_task_id = str(task["id"])
                    worker_statuses[current_task_id] = task
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
                if task.get("id"):
                    current_task_id = str(task["id"])
                    completed_task_ids.add(current_task_id)
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
                last_progress_detail = "任务完成" if task.get("success") else "任务失败"
                _set_spinner_message(_collaboration_progress_message())
            elif event.type == "adversarial_complete":
                adversarial = event.adversarial or {}
                labels = {
                    "not_refuted": "未推翻",
                    "refuted": "发现反例",
                    "inconclusive": "结果不确定",
                }
                status = adversarial.get("status", "inconclusive")
                color = "yellow" if status != "not_refuted" else "green"
                console.print(
                    f"\n[bold {color}]对抗测试：{labels.get(status, status)}[/]"
                )
                for finding in adversarial.get("findings", []):
                    console.print(f"  ⚠ {finding}")
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
            elif event.type == "error":
                error_text = event.error or "协作执行失败"
                console.print(f"\n[bold red]✖ 执行错误：{error_text}[/bold red]")
            elif event.type == "done":
                tool_calls = event.tool_calls
                files_written = event.files_written
                input_tokens = event.input_tokens
                output_tokens = event.output_tokens
                cost_usd = event.cost_usd
                final_content = event.assistant_message
    finally:
        _stop_spinner()
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
    configured_main_model = agent.gateway.get_main_model() or "unknown"
    main_model = engineering_routed_model or configured_main_model
    if is_collaboration:
        model_line = f"主模型：{main_model}"
        if models_used:
            model_line += f" | 协作模型：{', '.join(sorted(models_used))}"
    else:
        model_line = f"模型：{main_model}"
    if main_model != configured_main_model:
        model_line += f"（配置主模型：{configured_main_model}）"

    console.print(
        f"[dim]{model_line}  |  输入 token: {input_tokens}  输出 token: {output_tokens}  "
        f"成本: ${cost_usd:.6f}[/dim]"
    )
    if engineering_routing_reason:
        console.print(
            f"[dim]模型路由：{engineering_routing_source or 'unknown'} · "
            f"{engineering_routing_reason}[/dim]"
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

    return {
        "last_in": int(input_tokens or 0),
        "last_out": int(output_tokens or 0),
        "last_cost": float(cost_usd or 0.0),
    }


def _cmd_new(store: SessionStore, title: str = ""):
    session = store.create(title=title)
    console.print(f"[bold green]已创建新会话：{session.id}[/bold green]")
    return session


def _print_recovery_notice(session) -> bool:
    state = SessionRecoveryManager(session).inspect()
    if not state.required:
        return False
    steps = (
        "\n".join(f"  - {item['title']} [{item['status']}]" for item in state.unfinished_steps)
        or "  - 无结构化步骤；上次 run 状态需要人工确认"
    )
    console.print(Panel(
        f"状态：{state.run_status}\n"
        f"原因：{state.reason}\n"
        f"未完成步骤：{state.unfinished_step_count}\n{steps}\n\n"
        "输入 /resume continue 继续未完成部分，或 /resume abandon 放弃。\n"
        "确认前不会调用模型、执行工具或自动重放。",
        title="检测到中断任务",
        border_style="yellow",
    ))
    return True


def _cmd_load(store: SessionStore, session_id: str):
    try:
        session = store.load(session_id)
        console.print(f"[bold green]已加载会话：{session.id}[/bold green]")
        _print_recovery_notice(session)
        return session
    except FileNotFoundError:
        console.print(f"[bold red]会话不存在：{session_id}[/bold red]")
        return None


def _cmd_resume(store: SessionStore, session, action: str) -> bool:
    normalized = action.strip().lower()
    if normalized not in {"continue", "abandon"}:
        console.print("[bold red]用法：/resume <continue|abandon>[/bold red]")
        return False
    manager = SessionRecoveryManager(session)
    try:
        manager.decide(normalized)
    except ValueError as exc:
        console.print(f"[bold red]{exc}[/bold red]")
        return False
    store.save(session)
    if normalized == "continue":
        console.print(
            "[bold green]已确认继续。下一条消息会创建新 run，且只携带未完成步骤检查点。[/bold green]"
        )
    else:
        console.print(
            "[dim]已放弃中断任务；既有文件和证据保持原样，未执行回滚或重放。[/dim]"
        )
    return True


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


def _cmd_report(session, scope: str = "session") -> None:
    """Aggregate all local RunJournals without a model call."""
    from src.core.engineering import (
        DeliveryReportBuilder,
        RunJournalStore,
        load_today_journals,
    )

    normalized = scope.strip().casefold() or "session"
    if normalized not in {"session", "today"}:
        console.print("用法：/report [session|today]", style="bold red", markup=False)
        return
    if normalized == "today":
        sessions_root = Path(session.output_dir).resolve().parent.parent
        journals = load_today_journals(sessions_root)
        report = DeliveryReportBuilder().build(journals, scope="today")
    else:
        journals = RunJournalStore.from_output_dir(session.output_dir).list()
        report = DeliveryReportBuilder().build(
            journals, scope="session", session_id=session.id
        )
    console.print(Markdown(report.to_markdown()))
    console.print(
        "[dim]报告仅聚合本地 RunJournal 直接证据，未调用模型、未产生 token。[/dim]"
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
    if journal.model_routing is not None:
        routing = journal.model_routing
        console.print(
            f"模型路由：{routing.requested_model or '无'} → "
            f"{routing.selected_model or '无'}（{routing.source}）"
        )
        console.print(f"路由理由：{routing.reason}")
        console.print(
            f"价格比较：{routing.price_comparison}；"
            f"允许节省声明：{'是' if routing.savings_claim_allowed else '否'}；"
            f"升级次数：{routing.upgrade_count}/{routing.max_upgrades}"
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
            f"读取 {stats.get('read', 0)} 个，复用 {stats.get('reused', 0)} 个，"
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
    config_path = getattr(gateway, "config_path", "config/providers.yaml")
    console.print(f"[dim]配置：{config_path} · 工作目录：{Path.cwd()}[/dim]")
    console.print(
        "[dim]说明：CLI 与 Web「测试连接」都应读同一项目下的 .env；"
        "若 Key 显示 unresolved_env_ref，说明变量未展开。[/dim]"
    )
    for model_name in gateway.models:
        model_cfg = gateway.models[model_name]
        key_status = gateway.describe_key_status(model_cfg.provider)
        result = gateway.test_model(model_name)
        detail = (
            result.get("error", "")
            if not result.get("success")
            else f"{result.get('response_time_ms', 0):.0f}ms"
        )
        line = Text(f"  {model_name}: ")
        if result.get("success"):
            line.append("✅ 正常", style="green")
        else:
            line.append("❌ 失败", style="red")
        line.append(
            f"  [provider={model_cfg.provider} key={key_status}]",
            style="dim",
        )
        if detail:
            line.append(f" {detail}")
        console.print(line)
        if not result.get("success") and "unresolved" in key_status:
            console.print(
                Text(
                    f"    → Key 未解析。请确认在「{Path.cwd()}」下有 .env，"
                    f"且存在与 Provider 名对应的变量"
                    f"（如 provider「deepseek」→ DEEPSEEK_API_KEY）。"
                    f"Web 能通而 CLI 不通时，多半是终端启动目录与 Web 不是同一项目。",
                    style="yellow",
                )
            )
    console.print(
        "[dim]可恢复的失败模型会进入健康冷却；认证或配置错误不会自动切换。[/dim]"
    )


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


def _set_mode(session, agent, mode_ref: list[str], mode: str, *, quiet: bool = False) -> bool:
    """设置会话权限模式。

    quiet=True 时不打印（用于 Shift+Tab 即时同步，避免刷屏）。
    """
    if mode not in MODES:
        console.print(f"[bold red]未知模式：{mode}，可选：{' / '.join(MODES)}[/bold red]")
        return False
    session.approval_mode = mode  # type: ignore[assignment]
    agent.approval_mode = mode  # type: ignore[assignment]
    mode_ref[0] = mode
    if not quiet:
        style = _mode_rich_style(mode)
        console.print(f"[{style}]已切换权限模式：{mode}[/{style}]")
        console.print("[dim]（当前模式请看屏幕底部工具栏）[/dim]")
    return True


def _set_depth(session, depth: str) -> bool:
    """设置持久化执行深度；安全下限仍由每轮任务合同决定。"""
    if depth not in DEPTHS:
        console.print(
            f"[bold red]未知执行深度：{depth}，可选：{' / '.join(DEPTHS)}[/bold red]"
        )
        return False
    session.execution_depth = depth
    console.print(f"[cyan]已设置执行深度：{depth}[/cyan]")
    if depth != "auto":
        console.print("[dim]高风险任务仍会按不可绕过的验证边界自动提升。[/dim]")
    return True


def _set_collaboration_mode(session, mode: str) -> bool:
    """Persist single-Agent vs explicit multi-model collaboration."""
    if mode not in COLLAB_MODES:
        console.print(
            f"[bold red]未知协作模式：{mode}，可选：{' / '.join(COLLAB_MODES)}[/bold red]"
        )
        return False
    session.collaboration_mode = mode
    labels = {
        "auto": "自动：仅 deep 的修改/构建进入多模型",
        "single": "强制单 Agent",
        "multi": "强制多模型（仍受只读/Plan/任务策略约束）",
    }
    console.print(f"[cyan]已设置协作模式：{mode}（{labels[mode]}）[/cyan]")
    return True


def _set_routing_mode(session, mode: str) -> bool:
    """设置自动路由或固定使用用户主模型。"""
    if mode not in ROUTING_MODES:
        console.print(
            f"[bold red]未知路由模式：{mode}，可选："
            f"{' / '.join(ROUTING_MODES)}[/bold red]"
        )
        return False
    session.model_routing_mode = mode
    label = "自动选择并保守回退" if mode == "auto" else "固定使用主模型"
    console.print(f"[cyan]已设置模型路由：{mode}（{label}）[/cyan]")
    return True


def _set_adversarial_testing(session, state: str) -> bool:
    """Persist the opt-in experimental adversarial testing switch."""
    normalized = state.strip().lower()
    if normalized not in {"on", "off"}:
        console.print("[bold red]未知对抗测试状态，可选：on / off[/bold red]")
        return False
    session.adversarial_testing = normalized == "on"
    label = "已启用" if session.adversarial_testing else "已关闭"
    console.print(f"[cyan]实验对抗测试：{label}[/cyan]")
    if session.adversarial_testing:
        console.print(
            "[dim]仅 deep 的 change/build 多模型协作会额外调用只读对抗角色。[/dim]"
        )
    return True


def _checkpoint_store(session) -> "WorkspaceCheckpointStore":
    from src.core.checkpoint import WorkspaceCheckpointStore

    store_dir = Path(session.output_dir).resolve().parent / "checkpoints"
    return WorkspaceCheckpointStore(store_dir, Path.cwd())


def _cmd_checkpoint(session, argument: str) -> bool:
    """Mutate session only for `/checkpoint auto`. Returns True when it should be saved."""
    parts = argument.split()
    action = (parts[0] if parts else "create").strip().lower()
    rest = parts[1:]
    try:
        store = _checkpoint_store(session)
        if action in {"", "create"}:
            manifest = store.create()
            console.print(
                f"[cyan]已创建检查点 {manifest.id}（{manifest.file_count} 个文件；"
                f"跳过敏感 {manifest.skipped_sensitive} / 过大 {manifest.skipped_large}）。[/cyan]"
            )
            if manifest.pruned:
                console.print(f"[dim]已清理旧检查点 {len(manifest.pruned)} 个。[/dim]")
            console.print("[dim]快照不写入用户 .git。恢复前请 /checkpoint preview。[/dim]")
            return False
        if action == "list":
            items = store.list()
            if not items:
                console.print("[dim]当前会话没有检查点。[/dim]")
                return False
            usage = store.usage()
            console.print(
                f"[dim]共 {usage['count']} 个检查点，约 {usage['bytes']:,} 字节。[/dim]"
            )
            for item in items:
                console.print(
                    f"  {item.id}  {item.created_at}  {item.file_count} files  {item.source}"
                )
            return False
        if action in {"preview", "show"}:
            checkpoint_id = rest[0] if rest else ""
            if not checkpoint_id:
                items = store.list()
                if not items:
                    console.print("[bold red]没有可预览的检查点。[/bold red]")
                    return False
                checkpoint_id = items[0].id
            preview = store.preview(checkpoint_id)
            changing = preview.would_change
            if not changing:
                console.print(f"[dim]检查点 {checkpoint_id} 与当前工作区一致。[/dim]")
                return False
            for item in changing[:40]:
                console.print(f"  {item.kind:8} {item.path}")
            if preview.dirty_conflicts:
                console.print(
                    "[yellow]与用户未提交改动冲突：[/yellow] "
                    + "、".join(preview.dirty_conflicts[:12])
                )
            return False
        if action == "restore":
            if not rest:
                console.print(
                    "[bold red]用法：/checkpoint restore <id> confirm [overwrite-dirty][/bold red]"
                )
                return False
            checkpoint_id = rest[0]
            confirm = "confirm" in rest[1:]
            overwrite = "overwrite-dirty" in rest[1:]
            result = store.restore(
                checkpoint_id, confirm=confirm, overwrite_dirty=overwrite
            )
            if result.restored:
                console.print(
                    f"[green]已从 {result.checkpoint_id} 恢复 {len(result.restored_files)} 个文件。[/green]"
                )
            else:
                console.print(f"[yellow]{result.reason}[/yellow]")
                if result.dirty_conflicts:
                    console.print("冲突文件：" + "、".join(result.dirty_conflicts))
            return False
        if action == "auto":
            if not rest:
                state = "on" if session.auto_checkpoint else "off"
                console.print(f"写前自动检查点：{state}；可选：on / off")
                return False
            value = rest[0].strip().lower()
            if value not in {"on", "off", "true", "false", "1", "0"}:
                console.print("[bold red]用法：/checkpoint auto on|off[/bold red]")
                return False
            session.auto_checkpoint = value in {"on", "true", "1"}
            state = "on" if session.auto_checkpoint else "off"
            console.print(f"[cyan]已设置写前自动检查点：{state}[/cyan]")
            return True
        if action == "prune":
            deleted = store.prune()
            usage = store.usage()
            if deleted:
                console.print(
                    f"[cyan]已清理 {len(deleted)} 个旧检查点；剩余 {usage['count']} 个"
                    f"（约 {usage['bytes']:,} 字节）。[/cyan]"
                )
            else:
                console.print(
                    f"[dim]无需清理；当前 {usage['count']} 个检查点"
                    f"（约 {usage['bytes']:,} 字节）。[/dim]"
                )
            return False
        console.print(
            "[bold red]用法：/checkpoint [create|list|preview|restore|auto|prune][/bold red]"
        )
    except FileNotFoundError as exc:
        console.print(f"[bold red]{exc}[/bold red]")
    return False


def _cmd_status(agent: Agent) -> dict[str, Any]:
    """Show session, recovery, and last-run facts without calling a model."""
    status = agent.get_session_status()
    budget = int(status.get("input_budget_tokens") or 0)
    current = int(status.get("current_tokens") or 0)
    usage = (current / budget * 100) if budget > 0 else 0.0
    recovery = (
        f"需要 /resume（{status.get('recovery_reason') or status.get('recovery_run_id')}）"
        if status.get("recovery_required")
        else "无"
    )
    last_run = status.get("last_run_status") or "无"
    last_verify = status.get("last_verification") or "无"
    collab_extra = status.get("collaboration_trigger_reason") or "尚未记录"
    lines = [
        f"权限模式：{status.get('approval_mode')}",
        f"执行深度：{status.get('execution_depth')}",
        f"协作模式：{status.get('collaboration_mode')}（最近原因：{collab_extra}）",
        f"写前自动检查点：{'开' if status.get('auto_checkpoint') else '关'}"
        + (
            f"（最近：{status.get('last_workspace_checkpoint')}）"
            if status.get("last_workspace_checkpoint")
            else ""
        ),
        f"模型路由：{status.get('model_routing_mode')}",
        f"当前模型：{status.get('model_alias') or '-'} / {status.get('provider') or '-'}",
        f"Plan 模式：{status.get('plan_mode')}",
        f"上下文：{current:,} / {budget:,} tokens（{usage:.1f}%）",
        f"最近 run：{last_run}",
        f"最近验证：{last_verify}",
        f"中断恢复：{recovery}",
        "本命令不调用模型、不执行工具。",
    ]
    console.print(Panel("\n".join(lines), title="会话状态", border_style="cyan"))
    return status


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
    compaction_count = status.get("compaction_count", 0)
    if compaction_count:
        lines.append(f"已压缩：{compaction_count} 次")
        for event in status.get("recent_compactions", [])[-1:]:
            lines.append(
                f"最近压缩：{event.get('at', '')}，"
                f"{event.get('before_tokens', 0):,} → {event.get('after_tokens', 0):,} tokens，"
                f"合并 {event.get('dropped_messages', 0)} 条消息"
            )
    for obs in status.get("usage_observations", [])[-1:]:
        lines.append(
            f"估算误差：{obs.get('error_pct', 0)}%"
            f"（估算 {obs.get('estimated_input', 0):,} / 实际 {obs.get('actual_input', 0):,}）"
        )
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
    # 加载已启用插件（幂等），失败隔离不影响核心功能
    from src.plugins.runtime import load_plugins

    plugin_result = load_plugins()
    if plugin_result.loaded:
        console.print(
            Text(
                f"已加载 {plugin_result.loaded} 个插件："
                f"{', '.join(plugin_result.loaded_ids)}",
                style="cyan",
            )
        )
    for diagnostic in plugin_result.diagnostics[:3]:
        console.print(
            Text(
                f"  - 插件 {diagnostic.get('entry', '?')}: {diagnostic['message']}",
                style="yellow",
            )
        )
    agent = Agent(gateway, session, memory_store=memory_store)

    def _on_mode_change(mode: str) -> None:
        """Shift+Tab 时立刻写入 session/agent，避免只改了底部栏、逻辑仍是旧模式。"""
        if mode not in MODES:
            return
        session.approval_mode = mode  # type: ignore[assignment]
        agent.approval_mode = mode  # type: ignore[assignment]

    # 底部栏实时 token 用量（本轮 + 会话累计）
    usage_ref: dict[str, Any] = {
        "last_in": 0,
        "last_out": 0,
        "last_cost": 0.0,
        "total_in": 0,
        "total_out": 0,
        "total_cost": 0.0,
    }

    def _refresh_usage(last: dict[str, Any] | None = None) -> None:
        if last:
            usage_ref["last_in"] = int(last.get("last_in", 0) or 0)
            usage_ref["last_out"] = int(last.get("last_out", 0) or 0)
            usage_ref["last_cost"] = float(last.get("last_cost", 0.0) or 0.0)
        try:
            summary = gateway.billing.summary()
            usage_ref["total_in"] = int(summary.get("total_input_tokens", 0) or 0)
            usage_ref["total_out"] = int(summary.get("total_output_tokens", 0) or 0)
            usage_ref["total_cost"] = float(summary.get("total_cost_usd", 0.0) or 0.0)
        except Exception:
            pass

    pt_session = _make_prompt_session(
        mode_ref,
        on_mode_change=_on_mode_change,
        usage_ref=usage_ref,
    )

    _print_welcome(session.id, mode_ref[0])

    try:
        while True:
            try:
                user_input = pt_session.prompt(_prompt_message).strip()
            except (EOFError, KeyboardInterrupt):
                console.print("\n退出对话。")
                break

            if not user_input:
                continue

            # 同步 agent 与 session 的模式（Shift+Tab 已即时写入；命令路径安静对齐）
            if agent.approval_mode != mode_ref[0] or session.approval_mode != mode_ref[0]:
                _set_mode(session, agent, mode_ref, mode_ref[0], quiet=True)

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
                    pt_session = _make_prompt_session(
                        mode_ref,
                        on_mode_change=_on_mode_change,
                        usage_ref=usage_ref,
                    )
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
                        pt_session = _make_prompt_session(
                            mode_ref,
                            on_mode_change=_on_mode_change,
                            usage_ref=usage_ref,
                        )
                        agent = Agent(gateway, session, memory_store=memory_store)
                elif cmd == "/resume":
                    if _cmd_resume(store, session, arg):
                        agent = Agent(gateway, session, memory_store=memory_store)
                elif cmd == "/save":
                    store.save(session)
                    console.print(f"[bold green]已保存会话：{session.id}[/bold green]")
                elif cmd == "/sessions":
                    _cmd_sessions(store)
                elif cmd == "/runs":
                    _cmd_runs(session, arg)
                elif cmd == "/report":
                    _cmd_report(session, arg)
                elif cmd == "/context":
                    _cmd_context(agent)
                elif cmd == "/status":
                    _cmd_status(agent)
                elif cmd == "/checkpoint":
                    if _cmd_checkpoint(session, arg):
                        store.save(session)
                elif cmd == "/tree":
                    _cmd_tree(arg)
                elif cmd == "/plan":
                    if not arg:
                        console.print(
                            "[bold red]用法：/plan <需求>，或 /plan enter/show/revise/approve/cancel[/bold red]"
                        )
                        continue
                    plan_parts = arg.split(" ", 1)
                    plan_action = plan_parts[0].strip().lower()
                    plan_arg = plan_parts[1].strip() if len(plan_parts) > 1 else ""
                    if plan_action == "enter":
                        session.enter_plan_mode(plan_arg)
                        store.save(session)
                        console.print(
                            "[bold cyan]已进入 Plan 模式。下一条消息只会侦察和制定方案，不会修改项目。[/bold cyan]"
                        )
                    elif plan_action == "show":
                        artifact = session.plan_artifact
                        if artifact is None:
                            console.print("[dim]当前没有 Plan 方案。[/dim]")
                        else:
                            body = artifact.content or "（方案尚未生成）"
                            console.print(
                                Panel(
                                    Markdown(body),
                                    title=f"Plan · {session.plan_mode} · revision {artifact.revision}",
                                    border_style="cyan",
                                )
                            )
                    elif plan_action == "revise":
                        if not plan_arg:
                            console.print("[bold red]用法：/plan revise <意见>[/bold red]")
                            continue
                        try:
                            session.request_plan_revision(plan_arg)
                        except ValueError as exc:
                            console.print(f"[bold red]{exc}[/bold red]")
                        else:
                            store.save(session)
                            console.print("[cyan]已记录修订意见，请发送下一条消息生成新版方案。[/cyan]")
                    elif plan_action == "approve":
                        try:
                            approved_plan = session.approve_plan()
                        except ValueError as exc:
                            console.print(f"[bold red]{exc}[/bold red]")
                        else:
                            store.save(session)
                            implementation_request = (
                                "请严格按照下面已经批准的方案开始实施；遵守当前项目规则和权限规则，"
                                "完成后运行与风险匹配的验证。\n\n" + approved_plan
                            )
                            last = asyncio.run(
                                _stream_turn(
                                    agent,
                                    implementation_request,
                                    mode_ref=mode_ref,
                                    session=session,
                                    store=store,
                                )
                            )
                            _refresh_usage(last)
                            store.save(session)
                    elif plan_action == "cancel":
                        session.cancel_plan_mode()
                        store.save(session)
                        console.print("[dim]已取消 Plan 模式。[/dim]")
                    else:
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
                elif cmd == "/depth":
                    if not arg:
                        console.print(
                            f"当前执行深度：{session.execution_depth}；"
                            f"可选：{' / '.join(DEPTHS)}"
                        )
                    elif _set_depth(session, arg.strip().lower()):
                        store.save(session)
                elif cmd == "/collab":
                    if not arg:
                        console.print(
                            f"当前协作模式：{session.collaboration_mode}；"
                            f"可选：{' / '.join(COLLAB_MODES)}"
                        )
                    elif _set_collaboration_mode(session, arg.strip().lower()):
                        store.save(session)
                elif cmd == "/routing":
                    if not arg:
                        console.print(
                            f"当前模型路由：{session.model_routing_mode}；"
                            f"可选：{' / '.join(ROUTING_MODES)}"
                        )
                    elif _set_routing_mode(session, arg.strip().lower()):
                        store.save(session)
                elif cmd == "/adversarial":
                    if not arg:
                        status = "on" if session.adversarial_testing else "off"
                        console.print(f"当前实验对抗测试：{status}；可选：on / off")
                    elif _set_adversarial_testing(session, arg):
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
                if _print_recovery_notice(session):
                    continue
                last = asyncio.run(
                    _stream_turn(
                        agent,
                        user_input,
                        mode_ref=mode_ref,
                        session=session,
                        store=store,
                    )
                )
                _refresh_usage(last)
                store.save(session)
            except KeyboardInterrupt:
                agent.interrupt_turn()
                console.print(
                    "\n[yellow]已中断本轮。工程记录不会停在 running；"
                    "需要继续时用 /resume continue，放弃用 /resume abandon。[/yellow]"
                )
                store.save(session)
            except Exception as e:
                console.print(Text(f"错误：{e}", style="bold red"))

    finally:
        from src.tools.extensions import shutdown_extensions

        shutdown_extensions()
        store.save(session)
        console.print(f"\n[bold]会话已保存：{session.id}[/bold]")
        gateway.print_billing()
