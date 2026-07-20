from pathlib import Path


old_missing = not Path("config.ini").exists()
new_text = Path("config.yaml").read_text(encoding="utf-8") if Path("config.yaml").is_file() else ""
raise SystemExit(0 if old_missing and "port: 8080" in new_text else 1)
