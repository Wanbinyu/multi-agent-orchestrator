"""Installed entry point for the local Web UI."""
from __future__ import annotations

import argparse
import webbrowser

import uvicorn


def serve(host: str = "127.0.0.1", port: int = 8123, *, open_browser: bool = True) -> None:
    """Run the WebUI for both `mao web` and the legacy `mao-ui` command."""
    url = f"http://{host}:{port}"
    print(f"MAO Web UI: {url}")
    if open_browser:
        webbrowser.open(url)
    uvicorn.run("src.ui.app:app", host=host, port=port, log_level="info")


def main() -> None:
    parser = argparse.ArgumentParser(description="启动 MAO Web UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8123)
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args()

    serve(host=args.host, port=args.port, open_browser=not args.no_open)


if __name__ == "__main__":
    main()
