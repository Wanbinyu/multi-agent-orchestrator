"""Non-blocking hotkeys during long-running CLI turns (Windows / POSIX)."""
from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Any


def poll_mode_hotkey() -> str | None:
    """If the user pressed a mode key, return the mode name; else None.

    Keys (no Enter needed on Windows console):
    - a / A  → auto
    - p / P  → approve  (permission)
    - r / R  → readonly
    """
    try:
        if sys.platform == "win32":
            import msvcrt

            if not msvcrt.kbhit():
                return None
            ch = msvcrt.getwch()
            # Arrow/function keys start with \\x00 or \\xe0
            if ch in ("\x00", "\xe0"):
                if msvcrt.kbhit():
                    extended = msvcrt.getwch()
                    # Windows console commonly reports Shift+Tab as
                    # 0x00/0x0f.  Windows Terminal may send the ANSI form
                    # below, handled in the escape branch.
                    if extended == "\x0f":
                        return "cycle"
                return None
            if ch == "\x1b":
                # Windows Terminal can expose Shift+Tab as ESC [ Z.
                sequence = ""
                while msvcrt.kbhit() and len(sequence) < 2:
                    sequence += msvcrt.getwch()
                if sequence == "[Z":
                    return "cycle"
                return None
            return _map_key(ch)
        # POSIX: non-blocking stdin
        import select

        if not sys.stdin.isatty():
            return None
        ready, _, _ = select.select([sys.stdin], [], [], 0)
        if not ready:
            return None
        ch = sys.stdin.read(1)
        if ch == "\x1b":
            sequence = sys.stdin.read(2)
            if sequence == "[Z":
                return "cycle"
            return None
        return _map_key(ch)
    except Exception:
        return None


def _map_key(ch: str) -> str | None:
    key = (ch or "").strip().casefold()
    if key in {"a"}:
        return "auto"
    if key in {"p"}:
        return "approve"
    if key in {"r"}:
        return "readonly"
    return None


def apply_hotkey_if_any(
    *,
    mode_ref: list[str] | None,
    on_mode_change: Callable[[str], Any] | None,
    announce: Callable[[str], None] | None = None,
) -> str | None:
    """Poll once; if mode changes, update mode_ref / callback and return new mode."""
    mode = poll_mode_hotkey()
    if not mode:
        return None
    if mode == "cycle":
        current = mode_ref[0] if mode_ref and mode_ref[0] else "approve"
        modes = ("auto", "approve", "readonly")
        index = modes.index(current) if current in modes else 0
        mode = modes[(index + 1) % len(modes)]
    if mode_ref is not None and mode_ref and mode_ref[0] == mode:
        return None
    if mode_ref is not None and mode_ref:
        mode_ref[0] = mode
    if on_mode_change is not None:
        try:
            on_mode_change(mode)
        except Exception:
            pass
    if announce is not None:
        try:
            announce(mode)
        except Exception:
            pass
    return mode
