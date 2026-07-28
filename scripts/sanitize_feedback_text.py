"""Redact common secrets from feedback text before pasting into Issues.

Reads a file path argument or stdin; writes sanitized text to stdout.
Never phone-home. Intended for local use only.

Examples:
  python scripts/sanitize_feedback_text.py log.txt
  type log.txt | python scripts/sanitize_feedback_text.py
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Order matters: longer / more specific first where possible.
_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._\-+/=]{8,}"), "Bearer ***"),
    (re.compile(r"\bsk-[A-Za-z0-9_\-]{10,}"), "sk-***"),
    (re.compile(r"\bark-[A-Za-z0-9_\-]{10,}"), "ark-***"),
    (re.compile(r"\bghp_[A-Za-z0-9]{20,}"), "ghp_***"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"), "github_pat_***"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"), "xox*-***"),
    (re.compile(r"(?i)\b(api[_-]?key|access[_-]?token|secret|password)\s*[:=]\s*\S+"),
     r"\1=***"),
    (re.compile(r"(?i)(authorization\s*:\s*)\S+"), r"\1***"),
    # Query token-like parameters
    (re.compile(r"([?&](?:token|key|api_key|access_token)=)[^&\s]+", re.I), r"\1***"),
    # Windows user path: keep drive, redact home segment lightly
    (re.compile(r"(?i)([A-Z]:\\Users\\)[^\\\/\s]+"), r"\1<user>"),
    (re.compile(r"(?i)(/home/)[^/\s]+"), r"\1<user>"),
    (re.compile(r"(?i)(/Users/)[^/\s]+"), r"\1<user>"),
]


def sanitize(text: str) -> str:
    out = text
    for pattern, repl in _PATTERNS:
        out = pattern.sub(repl, out)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sanitize feedback text for public Issues")
    parser.add_argument(
        "path",
        nargs="?",
        help="Input file path; omit to read stdin",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Optional output file (default stdout)",
    )
    args = parser.parse_args(argv)

    if args.path:
        raw = Path(args.path).read_text(encoding="utf-8", errors="replace")
    else:
        raw = sys.stdin.read()

    cleaned = sanitize(raw)
    if args.output:
        Path(args.output).write_text(cleaned, encoding="utf-8")
    else:
        sys.stdout.write(cleaned)
        if cleaned and not cleaned.endswith("\n"):
            sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
