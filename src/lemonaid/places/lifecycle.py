"""Getting a session for a place, and tearing one down.

A "place" is just a directory. Creating a session for one and destroying one are
the same operations whether the directory already exists, has to be acquired
first, or is about to be released - so they share one path.
"""

from pathlib import Path

from .. import tmux
from ..config import Config, PlaceRoot
from ..log import get_logger
from . import hooks

_log = get_logger("places.lifecycle")

_ACQUIRE_TIMEOUT_SECONDS = 900  # acquiring a directory may install dependencies


def open_place(
    directory: Path,
    config: Config,
    session_name: str = "",
    attach: bool = True,
) -> str | None:
    """Switch to a session rooted at *directory*, creating one if none exists.

    Returns an error message on failure, or None on success.
    """
    session, pane_id = tmux.navigation.get_pane_for_cwd(str(directory))
    if session and pane_id:
        if not attach:
            return None  # it already exists; nothing to do but say so

        if not tmux.navigation.switch_to_pane(session, pane_id):
            return f"Could not switch to existing session '{session}'"

        return None

    return tmux.session.spawn_session(
        cwd=str(directory),
        config=config.tmux_session,
        session_name=session_name,
        attach=attach,
    )


def open_session(name: str, directory: Path, config: Config, attach: bool = True) -> str | None:
    """Get a session called *name* sitting in *directory*, acquiring nothing.

    For directories no root claims the names of, where a name can only have meant
    a session. Nothing is created or released on disk.

    Identity is the name, not the directory - unlike a place, where one directory
    means one session. Several differently-named sessions in the same directory is
    a normal thing to want here.
    """
    session, pane_id = tmux.navigation.get_pane_for_session(tmux.session.sanitize_name(name))
    if session and pane_id:
        if not attach:
            return None

        if not tmux.navigation.switch_to_pane(session, pane_id):
            return f"Could not switch to existing session '{session}'"

        return None

    return tmux.session.spawn_session(
        cwd=str(directory), config=config.tmux_session, session_name=name, attach=attach
    )


def open_key(
    key: str, config: Config, root: PlaceRoot, attach: bool = True
) -> tuple[Path | None, str | None]:
    """Get a session for *key* under *root*, acquiring its directory if needed.

    Idempotent at three levels: an existing directory is not re-created, an
    existing session is switched to rather than duplicated, and neither case is
    an error. So asking for a session is always safe, and no caller - person or
    agent - has to check first.

    Returns (directory, error message).
    """
    directory = hooks.directory_for_key(root, key)
    if directory is None:
        if not root.create:
            return None, f"No create command configured for {root.path}"

        _log.info("acquiring %r under %s", key, root.path)
        directory = hooks.create(root, key, timeout=_ACQUIRE_TIMEOUT_SECONDS)

    if directory is None:
        return None, f"Could not acquire a directory for {key!r} under {root.path}"

    return directory, open_place(directory, config, session_name=key, attach=attach)
