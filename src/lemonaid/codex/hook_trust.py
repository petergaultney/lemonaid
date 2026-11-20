"""Whether Codex runs one of lemonaid's hooks.json handlers, as Codex itself answers it.

Codex runs a handler only while it is enabled and trusted at its current hash. Trust
changes only when the hooks file or Codex's config does, so an answer is kept until
one of them changes.
"""

import functools
import os
from pathlib import Path

from . import app_server

_TIMEOUT = 5.0
_RUNS = ("trusted", "managed")


def _mtime(path: Path) -> int:
    try:
        return os.stat(path).st_mtime_ns
    except OSError:
        return 0


@functools.lru_cache(
    maxsize=64
)  # an exception isn't kept, so an unanswered question is asked again
def _runs(hooks_json: Path, event: str, status_message: str, _changed: tuple) -> bool:
    def ask(server: app_server.Server) -> bool:
        [reply] = server.ask([("hooks/list", {"cwds": [str(Path.home())]})], _TIMEOUT)
        if "error" in reply:
            raise app_server.NoAnswer(str(reply["error"]))

        return any(
            hook.get("eventName") == event
            and hook.get("sourcePath") == str(hooks_json)
            and hook.get("statusMessage") == status_message
            and hook.get("enabled") is not False
            and hook.get("trustStatus") in _RUNS
            for entry in reply["result"]["data"]
            for hook in entry.get("hooks", [])
        )

    if (answer := app_server.once(ask, f"{event} hooks", None, _TIMEOUT)) is None:
        raise app_server.NoAnswer("codex app-server did not answer")

    return answer


def session_end_runs(home: Path, hooks_json: Path, status_message: str) -> bool:
    """Whether Codex runs the user-level SessionEnd handler in *hooks_json* titled
    *status_message*. Codex that can't be asked counts as not running it."""
    changed = (_mtime(hooks_json), _mtime(home / "config.toml"))
    try:
        return _runs(hooks_json, "sessionEnd", status_message, changed)
    except app_server.NoAnswer:
        return False
