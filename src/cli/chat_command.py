"""CLI 交互式对话命令"""
from __future__ import annotations

import asyncio
import time
from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
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


COMMANDS = """
可用命令：
  /new [标题]      创建新会话
  /load <id>       加载已有会话
  /save            手动保存当前会话
  /sessions        列出最近会话
  /plan <需求>     使用 Orchestrator 执行一次性任务计划
  /memory add <分类> <内容>  添加长期记忆
  /memory list [分类]        列出长期记忆
  /memory search <查询>      搜索长期记忆
  /memory forget <id>        删除长期记忆
  /memory index              重建项目文件索引
  /memory summarize          总结当前会话并保存到记忆
  /mode <模式>     切换权限模式：auto / approve / readonly（也可直接输 /auto、/approve、/readonly）
  /auto            切换到自动执行模式
  /approve         切换到每次确认模式
  /readonly        切换到只读模式
  /tools           显示可用工具
  /help            显示此帮助
  /exit 或 /quit   退出

提示：
  - Shift+Tab 可快速切换模式
  - 权限询问时输入 auto/always 可临时切换到自动模式并批准当前请求
"""


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
        bottom_toolbar=lambda: HTML(
            f" Mode: <{_mode_color(mode_ref[0])}><b>{mode_ref[0]}</b></{_mode_color(mode_ref[0])}> "
            f"| Shift+Tab 切换 | /mode &lt;auto|approve|readonly&gt; "
        ),
    )


def _print_welcome(session_id: str, mode: str):
    mode_line = f"当前权限模式: [{_mode_rich_style(mode)}]{mode}[/{_mode_rich_style(mode)}]（auto=自动执行，approve=需批准，readonly=只读）"
    console.print(
        Panel.fit(
            f"进入 Multi-Agent Orchestrator 对话模式\n"
            f"会话 ID: {session_id}\n"
            f"{mode_line}\n"
            f"{COMMANDS}",
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

    def _start_spinner(message: str):
        nonlocal spinner_task
        if spinner_task is not None and not spinner_task.done():
            return

        async def _spin():
            frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
            i = 0
            start = time.monotonic()
            while True:
                elapsed = time.monotonic() - start
                try:
                    live.update(Markdown(f"{message} {frames[i % len(frames)]} ({elapsed:.1f}s)"))
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
        vertical_overflow="visible",
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
                    f"\n[bold {color}]🔍 审查结果：{status_text}[/{color}]"
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

    if is_collaboration and final_content:
        console.print(
            Panel(Markdown(final_content), title="📝 最终答案", border_style="green")
        )

    if tool_calls:
        console.print("[bold]🔧 工具调用[/bold]")
        for call in tool_calls:
            success = bool(call.get("success"))
            status = "✅" if success else "❌"
            color = "green" if success else "red"
            tool_name = call["tool"]
            params = call.get("params", {})

            if tool_name == "write_file":
                path = params.get("path", "未知文件")
                lines = len(params.get("content", "").splitlines())
                console.print(f"[{color}]● Update({path})  {lines} 行[/{color}]")
            elif tool_name == "read_file":
                path = params.get("path", "未知路径")
                console.print(f"[{color}]● Read({path})[/{color}]")
            elif tool_name == "run_command":
                command = params.get("command", "")
                console.print(f"[{color}]● Run({command})[/{color}]")
            elif tool_name == "web_search":
                query = params.get("query", "")
                console.print(f"[{color}]● WebSearch({query})[/{color}]")
            elif tool_name == "fetch_url":
                url = params.get("url", "")
                console.print(f"[{color}]● Fetch({url})[/{color}]")
            elif tool_name in ("search_project_files", "search_memory"):
                query = params.get("query", "")
                console.print(f"[{color}]● Search({query})[/{color}]")
            else:
                # 通用兜底：优先关键字段，否则显示全部参数
                summary = _summarize_params(params)
                console.print(f"[{color}]● {tool_name}({summary})[/{color}]")

    if files_written:
        file_text = Text("\n".join(f"✓ {f}" for f in files_written))
        console.print(Panel(file_text, title="📁 已写入文件", border_style="green"))

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

    load_extensions()
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
                elif cmd == "/help":
                    console.print(COMMANDS)
                else:
                    console.print(f"[bold red]未知命令：{cmd}，输入 /help 查看帮助[/bold red]")
                continue

            try:
                asyncio.run(_stream_turn(agent, user_input))
                store.save(session)
            except Exception as e:
                console.print(f"[bold red]错误：{e}[/bold red]")

    finally:
        store.save(session)
        console.print(f"\n[bold]会话已保存：{session.id}[/bold]")
        gateway.print_billing()
