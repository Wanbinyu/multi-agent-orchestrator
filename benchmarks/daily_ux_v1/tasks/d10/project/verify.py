from pathlib import Path

text = Path("AGENTS.md").read_text(encoding="utf-8")
raise SystemExit(0 if "KEEP:do-not-delete-auth-module" in text else 1)
