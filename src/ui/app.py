"""模型连接配置 UI 入口"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.ui.routers import chat, memory, providers

app = FastAPI(title="Multi-Agent Orchestrator - 模型连接配置")

# 静态资源与模板目录基于本文件位置解析，保证无论从哪启动都能找到
_base_dir = Path(__file__).parent
app.mount("/static", StaticFiles(directory=str(_base_dir / "static")), name="static")
templates = Jinja2Templates(directory=str(_base_dir / "templates"))

app.include_router(providers.router)
app.include_router(chat.router)
app.include_router(memory.router)


@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
