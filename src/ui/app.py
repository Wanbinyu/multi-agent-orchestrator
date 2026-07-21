"""模型连接配置 UI 入口"""
from __future__ import annotations

from contextlib import asynccontextmanager
import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

# The Web entry points import this module directly, bypassing run.py. Load local
# credentials before chat.router constructs its process-wide GatewayClient.
load_dotenv()

from src.ui.routers import chat, memory, providers
from src.gateway.errors import ProviderError, provider_error_http_status


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时加载 Hooks + MCP 工具源 + 已启用插件"""
    from src.tools.extensions import load_extensions, shutdown_extensions
    from src.plugins.runtime import load_plugins, shutdown_plugins

    extension_status = load_extensions()
    app.state.extension_status = extension_status
    if extension_status["diagnostics"]:
        logger.warning(
            "MAO skipped %d invalid optional extension entries; "
            "see GET /api/diagnostics/extensions",
            len(extension_status["diagnostics"]),
        )
    plugin_result = load_plugins()
    app.state.plugin_status = plugin_result.to_summary()
    if plugin_result.diagnostics:
        logger.warning(
            "MAO plugin loader reported %d issues; see GET /api/plugins",
            len(plugin_result.diagnostics),
        )
    try:
        yield
    finally:
        shutdown_plugins()
        shutdown_extensions()


app = FastAPI(title="Multi-Agent Orchestrator - 模型连接配置", lifespan=lifespan)

# 静态资源与模板目录基于本文件位置解析，保证无论从哪启动都能找到
_base_dir = Path(__file__).parent
app.mount("/static", StaticFiles(directory=str(_base_dir / "static")), name="static")
templates = Jinja2Templates(directory=str(_base_dir / "templates"))

app.include_router(providers.router)
app.include_router(chat.router)
app.include_router(memory.router)


@app.exception_handler(ProviderError)
async def provider_error_handler(_request: Request, exc: ProviderError):
    return JSONResponse(
        status_code=provider_error_http_status(exc),
        content={"detail": exc.user_message, "error": exc.to_dict()},
    )


@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/diagnostics/extensions")
async def extension_diagnostics() -> dict:
    """Expose bounded optional-extension status without affecting health."""
    from src.tools.extensions import get_extension_status

    return get_extension_status()
