"""Whether a Claude session delivers a pushed message instead of holding it for approval.

Measured on 2.1.299: a session holds a foreign socket message for approval only while in
`bypassPermissions` mode, unless `crossSessionInbound` is "accept"; every other mode
delivers it. Lemonaid can't see a hold from the socket, so it pushes only when the setting
is "accept", or when the session could never reach bypass mode.
"""

import json
import sys
import typing as ty
from pathlib import Path

from . import launch_args, session_socket

_MANAGED = {
    "darwin": Path("/Library/Application Support/ClaudeCode/managed-settings.json"),
    "linux": Path("/etc/claude-code/managed-settings.json"),
}
_BYPASS_FLAGS = ("--dangerously-skip-permissions", "--allow-dangerously-skip-permissions")


def _flag(argv: list[str], name: str) -> str:
    for i, arg in enumerate(argv):
        if arg == name and i + 1 < len(argv):
            return argv[i + 1]
        if arg.startswith(f"{name}="):
            return arg.split("=", 1)[1]
    return ""


def _load(source: str, cwd: str = "") -> dict:
    """A settings file (relative to *cwd*), or the JSON string `--settings` also accepts."""
    try:
        text = (
            source
            if source.lstrip().startswith("{")
            else (Path(cwd) / Path(source).expanduser()).read_text()
        )
        data = json.loads(text)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _settings_layers(argv: list[str], cwd: str) -> list[dict]:
    """The settings a session reads, highest precedence first."""
    project = Path(cwd) / ".claude"
    return [
        _load(str(_MANAGED[sys.platform])) if sys.platform in _MANAGED else {},
        _load(flagged, cwd) if (flagged := _flag(argv, "--settings")) else {},
        _load(str(project / "settings.local.json")),
        _load(str(project / "settings.json")),
        _load(str(session_socket.claude_dir() / "settings.json")),
    ]


def _first(layers: ty.Iterable[dict], get: ty.Callable[[dict], ty.Any]) -> ty.Any:
    return next((value for layer in layers if (value := get(layer)) is not None), None)


def accepts(argv: list[str], cwd: str) -> bool:
    layers = _settings_layers(argv, cwd)
    setting = _first(layers, lambda s: s.get("crossSessionInbound"))
    if setting is not None:
        return setting == "accept"

    default_mode = _first(layers, lambda s: (s.get("permissions") or {}).get("defaultMode"))
    return not (
        any(flag in argv for flag in _BYPASS_FLAGS)
        or _flag(argv, "--permission-mode") == "bypassPermissions"
        or default_mode == "bypassPermissions"
    )


def session_accepts(entry: session_socket.Session) -> bool:
    argv = launch_args.argv(entry.pid)
    return bool(argv) and accepts(argv, entry.cwd)


def session_setting(entry: session_socket.Session) -> str:
    """ "accepted" or "not accepted"; "unknown" when the session's launch arguments can't be read."""
    argv = launch_args.argv(entry.pid)
    if not argv:
        return "unknown"

    return "accepted" if accepts(argv, entry.cwd) else "not accepted"
