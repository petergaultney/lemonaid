"""Whether a pull request is known to have merged or closed, shared by every lemon.

The scout records a PR's state each time it reads GitHub; the inbox reads it back
without a network call. A PR nobody has recorded is treated as open.
"""

import os
import pathlib
import tempfile

from .log import get_logger

_log = get_logger("pr_states")


def _path(repo: str, number: str) -> pathlib.Path:
    state = os.environ.get("LEMONAID_STATE_DIR") or "~/.local/state/lemonaid"
    return pathlib.Path(state).expanduser() / "pr-states" / f"{repo.replace('/', '#')}#{number}"


def record(repo: str, number: str, state: str) -> None:
    """Save *state* (`OPEN`, `MERGED` or `CLOSED`) for the PR, unless it is already saved."""
    path = _path(repo, number)
    try:
        if path.read_text() == state:
            return

    except OSError:
        pass
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".")
        with os.fdopen(fd, "w") as stream:
            stream.write(state)
        os.replace(temporary, path)
    except OSError as error:
        _log.warning("could not record state of %s#%s: %s", repo, number, error)


def is_finished(repo: str, number: str) -> bool:
    """True when the PR is recorded as merged or closed."""
    try:
        return _path(repo, number).read_text() in ("MERGED", "CLOSED")
    except OSError:
        return False
