"""CLI mid-turn hotkey mapping."""
from src.cli.hotkeys import _map_key, apply_hotkey_if_any


def test_map_key_modes():
    assert _map_key("a") == "auto"
    assert _map_key("A") == "auto"
    assert _map_key("p") == "approve"
    assert _map_key("r") == "readonly"
    assert _map_key("x") is None


def test_apply_hotkey_updates_mode_ref(monkeypatch):
    from src.cli import hotkeys

    monkeypatch.setattr(hotkeys, "poll_mode_hotkey", lambda: "auto")
    mode_ref = ["approve"]
    seen: list[str] = []
    result = apply_hotkey_if_any(
        mode_ref=mode_ref,
        on_mode_change=seen.append,
    )
    assert result == "auto"
    assert mode_ref[0] == "auto"
    assert seen == ["auto"]


def test_shift_tab_cycles_mode(monkeypatch):
    from src.cli import hotkeys

    monkeypatch.setattr(hotkeys, "poll_mode_hotkey", lambda: "cycle")
    mode_ref = ["approve"]
    seen: list[str] = []

    result = apply_hotkey_if_any(
        mode_ref=mode_ref,
        on_mode_change=seen.append,
    )

    assert result == "readonly"
    assert mode_ref[0] == "readonly"
    assert seen == ["readonly"]
