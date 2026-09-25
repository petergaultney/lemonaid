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
WAITER_CHECK_COMMAND = "lemonaid claude waiter-check"


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


def _write(path: Path, settings: dict) -> None:
    """Replace the settings file whole: a partial write is a file Claude Code will not start with.

    The file is commonly a symlink into a dotfiles repo. Replacing the link itself would
    leave a plain file in its place and the dotfile behind, so the write goes to the target.
    """
    target = path.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".json.lemonaid-tmp")
    tmp.write_text(json.dumps(settings, indent=2) + "\n")
    tmp.replace(target)


def install(event: str, command: str, path: Path | None = None, dry_run: bool = False) -> str:
    """Add a hook running `command` on `event`. Returns the line to print."""
    path = path or settings_path()
    settings = _load(path)
    settings, changed = _with_hook(settings, event, command)

    if not changed:
        return f"{event} hook already installed in {path}"

    if dry_run:
        return f"would add {event} -> {command} in {path}"

    _write(path, settings)
    return f"installed {event} -> {command} in {path}"


def uninstall(event: str, command: str, path: Path | None = None) -> str:
    """Remove the `event` hook lemonaid installed for `command`, and nothing else."""
    path = path or settings_path()
    settings = _load(path)
    entries = settings.get("hooks", {}).get(event, [])

    kept = [entry for entry in entries if not _has_command([entry], command)]
    if len(kept) == len(entries):
        return f"no lemonaid {event} hook in {path}"

    if kept:
        settings["hooks"][event] = kept
    else:
        del settings["hooks"][event]

    _write(path, settings)
    return f"removed {event} hook from {path}"


def install_session_start(path: Path | None = None, dry_run: bool = False) -> str:
    return install("SessionStart", _SESSION_START_COMMAND, path, dry_run)


def uninstall_session_start(path: Path | None = None) -> str:
    return uninstall("SessionStart", _SESSION_START_COMMAND, path)
