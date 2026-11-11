"""Whether a harness reports a quit to lemonaid, so that one ending without a report crashed.

Claude reports through lemonaid's SessionEnd hook once it is in its user settings and no
settings file it reads for the session sets `disableAllHooks`. Codex runs the hook only
once it is trusted at its current hash and enabled, and reports a quit only with its
shared app-server daemon off: a session in the daemon reports nothing when quit.
Anything that can't be read counts as not reporting, so a stop is archived as before.
"""

import json
import typing as ty
from collections import abc
from pathlib import Path

from ..claude import install_hooks
from ..codex import daemon_setup, hook_trust
from ..log import get_logger
from . import install

_log = get_logger("hooks.end_reports")

_CLAUDE_MANAGED = Path("/Library/Application Support/ClaudeCode/managed-settings.json")


def _settings(path: Path) -> dict[str, ty.Any] | None:
    """*path*'s settings, {} when it doesn't exist, None when it can't be read."""
    try:
        found = json.loads(path.read_text())
    except FileNotFoundError:
        return {}
    except (ValueError, OSError) as exc:
        _log.warning("cannot read %s: %s", path, exc)
        return None

    return found if isinstance(found, dict) else None


def _project_settings(cwd: str) -> abc.Iterator[Path]:
    if not cwd:
        return

    for directory in (Path(cwd), *Path(cwd).parents):
        yield directory / ".claude" / "settings.json"
        yield directory / ".claude" / "settings.local.json"


def _claude(cwd: str) -> bool:
    user = _settings(install.settings_path("claude"))
    if not user or not install_hooks.has_command(
        user.get("hooks", {}).get("SessionEnd", []), install.session_end_command("claude")
    ):
        return False

    others = [_settings(path) for path in (_CLAUDE_MANAGED, *_project_settings(cwd))]
    return all(
        settings is not None and settings.get("disableAllHooks") is not True
        for settings in (user, *others)
    )


def reported(harness: str, cwd: str) -> bool:
    """Whether *harness*, run in *cwd*, tells lemonaid when someone quits it."""
    if harness == "claude":
        return _claude(cwd)

    if harness == "codex":
        home = daemon_setup.codex_home()
        return hook_trust.session_end_runs(
            home, install.settings_path("codex"), install.SESSION_END_CODEX
        ) and not daemon_setup.daemon_auto_start_warning(home)

    return False
