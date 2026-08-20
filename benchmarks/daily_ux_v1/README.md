# daily-ux-v1

Offline **daily UX** contracts for MAO (P0-9). Data kind is always `synthetic_contract`.

Do **not** treat scores as a model ranking. Live Provider runs need a separate owner authorization.

```bash
python -m pytest -q tests/test_daily_ux.py
```

Task IDs D01–D10 match [`docs/P0-缩小对Claude-Code日常体感差距清单.md`](../../docs/P0-缩小对Claude-Code日常体感差距清单.md) §4. Each task has `tags: [daily_ux]`, file/command acceptance, and empty or declared `allowed_mutations`.
