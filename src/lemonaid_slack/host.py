"""What lemonaid gives the plugin when it starts it (docs/source-plugins.md): a state
directory, its `[slack]` table, and the command that runs lemonaid itself.

Run by hand, with none of those set, the plugin falls back to lemonaid's default state
directory and an empty table, and finds `lemonaid` on PATH.
"""

import json
import logging
import os
import shlex
import subprocess
import tempfile
from pathlib import Path

_log = logging.getLogger("lemonaid_slack")


def state_dir() -> Path:
    if found := os.environ.get("LEMONAID_PLUGIN_STATE"):
        return Path(found)

    state = os.environ.get("LEMONAID_STATE_DIR") or "~/.local/state/lemonaid"
    return Path(state).expanduser() / "slack"


def table() -> dict:
    try:
        found = json.loads(os.environ.get("LEMONAID_PLUGIN_CONFIG") or "{}")
    except ValueError:
        return {}

    return found if isinstance(found, dict) else {}


def write_json(path: Path, value: object) -> None:
    """Replace *path* whole, so a crash leaves the old value or the new one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(json.dumps(value))
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def lemonaid(*args: str) -> bool:
    """Run a lemonaid command; whether it succeeded. Its failure is logged, not raised."""
    argv = [*shlex.split(os.environ.get("LEMONAID") or "lemonaid"), *args]
    try:
        done = subprocess.run(argv, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as error:
        _log.warning("could not run %s: %s", shlex.join(argv), error)
        return False

    if done.returncode:
        _log.warning("%s failed: %s", shlex.join(argv), done.stderr.strip())
    return done.returncode == 0
