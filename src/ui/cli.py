"""Installed entry point for the local Web UI."""
from __future__ import annotations

import argparse
import webbrowser

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="启动 MAO Web UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8123)
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args()

    url = f"http://{args.host}:{args.port}"
    print(f"MAO Web UI: {url}")
    if not args.no_open:
        webbrowser.open(url)
    uvicorn.run("src.ui.app:app", host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
