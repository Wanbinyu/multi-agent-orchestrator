"""Application-level safety guards for tools.

These checks reduce accidental damage and common prompt-injection paths.
They are **not** an OS or container sandbox: MAO still runs with the process
privileges of the local user.
"""
from __future__ import annotations

import ipaddress
import re
import socket
from pathlib import Path
from urllib.parse import urlparse

# Sensitive basenames / suffixes that commonly hold secrets. Models should not
# load these into context via file tools without the user opening them outside MAO.
_SENSITIVE_BASENAMES = {
    ".env",
    ".env.local",
    ".env.development",
    ".env.production",
    ".env.test",
    ".env.staging",
    ".netrc",
    ".npmrc",
    ".pypirc",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "credentials.json",
    "service-account.json",
    "secrets.yaml",
    "secrets.yml",
    "secrets.json",
    "auth.json",
    "token",
    "tokens",
}

_SENSITIVE_BASENAME_PREFIXES = (
    ".env.",
    "credentials.",
    "service-account",
    "secret.",
)

_SENSITIVE_SUFFIXES = (
    ".pem",
    ".p12",
    ".pfx",
    ".key",
    ".keystore",
    ".jks",
)

_SENSITIVE_DIR_PARTS = {
    ".ssh",
    ".gnupg",
    ".aws",
    ".azure",
    ".gcloud",
    ".kube",
    ".docker",
}

_BLOCKED_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
    "metadata",
    "metadata.google.internal",
    "metadata.goog",
}

_NODE_INLINE_FLAGS = {
    "-e",
    "--eval",
    "-p",
    "--print",
}

_NODE_PRELOAD_FLAGS = {
    "-r",
    "--require",
    "--import",
    "--loader",
    "--experimental-loader",
}


def is_sensitive_path(path: str | Path) -> bool:
    """Return True when a path looks like a credential or secret store."""
    try:
        resolved = Path(path).expanduser()
    except (OSError, RuntimeError, ValueError, TypeError):
        return False
    parts = [part.casefold() for part in resolved.parts]
    if any(part in _SENSITIVE_DIR_PARTS for part in parts):
        return True
    name = resolved.name.casefold()
    if name in {item.casefold() for item in _SENSITIVE_BASENAMES}:
        return True
    if any(name.startswith(prefix.casefold()) for prefix in _SENSITIVE_BASENAME_PREFIXES):
        return True
    if any(name.endswith(suffix.casefold()) for suffix in _SENSITIVE_SUFFIXES):
        return True
    return False


def sensitive_path_error(path: str | Path) -> str:
    return (
        f"敏感路径已阻止访问：{path}。"
        "API 密钥与私钥不应进入模型上下文；请在 MAO 外由用户自行打开，"
        "或从权限边界中排除该文件。"
    )


def _flag_name(arg: str) -> str:
    """Normalize CLI flags, including --flag=value forms."""
    low = arg.casefold()
    if low.startswith("--") and "=" in low:
        return low.split("=", 1)[0]
    return low


def _python_has_inline_c(args: list[str]) -> bool:
    """Detect python -c / -ic style inline code without rejecting -m module -c."""
    if any(_flag_name(arg) == "-m" for arg in args):
        return False
    for arg in args:
        low = arg.casefold()
        if low.startswith("--") or not low.startswith("-"):
            continue
        # -c, -cCODE, or short clusters containing c (-ic, -uic)
        if low == "-c" or low.startswith("-c"):
            return True
        if re.fullmatch(r"-[a-z0-9]*c[a-z0-9]*", low):
            return True
    return False


def _python_reads_stdin_script(args: list[str]) -> bool:
    """`python -` reads a program from stdin — treat as arbitrary code."""
    for arg in args:
        if arg == "-":
            return True
        # Stop at first non-option positional after options start resolving.
        if not arg.startswith("-"):
            return False
    return False


def has_dangerous_interpreter_invocation(argv: list[str]) -> bool:
    """True when argv would execute arbitrary inline/preload interpreter code."""
    if len(argv) < 2:
        return False
    executable = Path(argv[0]).name.casefold()
    if executable.endswith(".exe"):
        executable = executable[:-4]
    args = argv[1:]
    if executable in {"python", "python3", "py"}:
        return _python_has_inline_c(args) or _python_reads_stdin_script(args)
    if executable == "node":
        for arg in args:
            name = _flag_name(arg)
            if name in _NODE_INLINE_FLAGS or name in _NODE_PRELOAD_FLAGS:
                return True
            # Combined short forms: -eCODE is uncommon for node, but -pe exists.
            if name.startswith("-") and not name.startswith("--"):
                letters = name[1:]
                if "e" in letters or "p" in letters or "r" in letters:
                    return True
        return False
    return False


def is_blocked_fetch_host(hostname: str | None) -> bool:
    if not hostname:
        return True
    host = hostname.strip().rstrip(".").casefold()
    if not host:
        return True
    if host in _BLOCKED_HOSTNAMES:
        return True
    if host.endswith(".localhost") or host.endswith(".local"):
        return True
    # Literal IPs
    try:
        ip = ipaddress.ip_address(host)
        return _is_non_public_ip(ip)
    except ValueError:
        pass
    # Resolve DNS and reject if any answer is non-public (basic SSRF guard).
    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, OSError, ValueError):
        # Unresolvable hosts are not treated as blocked here; the HTTP client
        # will fail later. We only block clearly unsafe targets.
        return False
    for info in infos:
        addr = info[4][0]
        try:
            if _is_non_public_ip(ipaddress.ip_address(addr)):
                return True
        except ValueError:
            continue
    return False


def _is_non_public_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def validate_fetch_url(url: str) -> str | None:
    """Return an error message if the URL must not be fetched; else None."""
    raw = (url or "").strip()
    if not raw:
        return "URL 不能为空"
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https"):
        return f"不支持的协议：{parsed.scheme or '(空)'}"
    if not parsed.netloc:
        return "URL 缺少域名"
    if is_blocked_fetch_host(parsed.hostname):
        return (
            "禁止抓取本地、内网或链路本地地址（SSRF 防护）。"
            "fetch_url 仅用于公开 http(s) 网页。"
        )
    return None
