"""Add lemonaid's hooks to Claude Code's settings, without disturbing yours.

SessionStart is opt-in because it changes what the inbox contains: every session
registers itself at birth, so the inbox stops being "sessions that spoke to you"
and becomes "sessions that exist". That is the point - a session nobody has
talked to yet is exactly what a restore needs to find - but it is a different
inbox than the one you had, so it is a thing you turn on.

Edits are additive and idempotent: an existing hook with the same command is
left alone, and hooks lemonaid did not write are never touched.
"""

import json
import typing as ty
from pathlib import Path

_SESSION_START_COMMAND = "lemonaid claude session-start"


def settings_path() -> Path:
    return Path.home() / ".claude" / "settings.json"


def _load(path: Path) -> dict:
    if not path.exists():
        return {}

    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise ValueError(f"{path} is not valid JSON ({e}); fix it before installing hooks") from e


def _has_command(entries: ty.Iterable[dict], command: str) -> bool:
    return any(
        hook.get("command") == command
        for entry in entries
        for hook in entry.get("hooks", [])
        if isinstance(hook, dict)
    )


def _with_hook(settings: dict, event: str, command: str) -> tuple[dict, bool]:
    """`settings` plus a hook for `command`, and whether anything changed."""
    hooks = settings.setdefault("hooks", {})
    entries = hooks.setdefault(event, [])

    if _has_command(entries, command):
        return settings, False

    entries.append({"hooks": [{"type": "command", "command": command}]})
    return settings, True


def install_session_start(path: Path | None = None, dry_run: bool = False) -> str:
    """Add the SessionStart hook. Returns the line to print."""
    path = path or settings_path()
    settings = _load(path)
    settings, changed = _with_hook(settings, "SessionStart", _SESSION_START_COMMAND)

    if not changed:
        return f"SessionStart hook already installed in {path}"

    if dry_run:
        return f"would add SessionStart -> {_SESSION_START_COMMAND} in {path}"

    path.parent.mkdir(parents=True, exist_ok=True)
    # Written whole rather than in place: a partial write here is a settings
    # file Claude Code will not start with.
    tmp = path.with_suffix(".json.lemonaid-tmp")
    tmp.write_text(json.dumps(settings, indent=2) + "\n")
    tmp.replace(path)
    return f"installed SessionStart -> {_SESSION_START_COMMAND} in {path}"


def uninstall_session_start(path: Path | None = None) -> str:
    """Remove the SessionStart hook lemonaid installed, and nothing else."""
    path = path or settings_path()
    settings = _load(path)
    entries = settings.get("hooks", {}).get("SessionStart", [])

    kept = [entry for entry in entries if not _has_command([entry], _SESSION_START_COMMAND)]
    if len(kept) == len(entries):
        return f"no lemonaid SessionStart hook in {path}"

    if kept:
        settings["hooks"]["SessionStart"] = kept
    else:
        del settings["hooks"]["SessionStart"]

    tmp = path.with_suffix(".json.lemonaid-tmp")
    tmp.write_text(json.dumps(settings, indent=2) + "\n")
    tmp.replace(path)
    return f"removed SessionStart hook from {path}"
