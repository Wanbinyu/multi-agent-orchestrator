from pathlib import Path


text = Path("settings.txt").read_text(encoding="utf-8")
raise SystemExit(0 if text == "mode=production\n" else 1)
