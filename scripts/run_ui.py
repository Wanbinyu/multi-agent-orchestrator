"""一键启动模型连接配置 UI"""
from __future__ import annotations

import argparse
import webbrowser

import uvicorn

from src.ui.app import app


def main() -> None:
    parser = argparse.ArgumentParser(description="启动 Multi-Agent Orchestrator 模型连接配置 UI")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址（默认 127.0.0.1）")
    parser.add_argument("--port", type=int, default=8123, help="监听端口（默认 8123）")
    parser.add_argument("--no-open", action="store_true", help="不自动打开浏览器")
    args = parser.parse_args()

    url = f"http://{args.host}:{args.port}"
    print(f"🌐 配置 UI 即将启动: {url}")
    if not args.no_open:
        webbrowser.open(url)

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
