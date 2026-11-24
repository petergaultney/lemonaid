"""Whether a run points only some of lemonaid's storage away from its defaults.

The database records which lemons hold which briefs, the state directory holds the audit
log and the stamps of what maintenance has run, and the briefs and mailboxes hold the
lemons' work. A run that redirects some of these and not the rest pairs a database with
briefs it has never recorded, so lemonaid refuses to run at all rather than act on that
pairing. The briefs and mailboxes are judged where the stores resolve them, cutover
included, and count as redirected only outside both live homes. A variable set to its
default redirects nothing: the scout host is started with `LEMONAID_DB` spelled out.
"""

import os
from pathlib import Path

from ..inbox import db
from . import layout


def default_state_dir() -> Path:
    return Path.home() / ".local" / "state" / "lemonaid"


def _briefs() -> Path:
    """Where `brief.store.briefs_dir` resolves."""
    override = os.environ.get("LEMONAID_BRIEFS_DIR")
    return Path(override) if override else layout.briefs_dir()


def _mailboxes() -> Path:
    """Where `messages.store.mailbox_root` resolves, without moving an old `inbox/`."""
    if override := os.environ.get("LEMONAID_MESSAGES_DIR"):
        return Path(override)

    if os.environ.get("LEMONAID_BRIEFS_DIR"):
        return _briefs() / layout.MAILBOX

    return layout.mailbox_root()


def _same(path: Path, default: Path) -> bool:
    return os.path.realpath(path) == os.path.realpath(default)


def _live(path: Path) -> bool:
    real = Path(os.path.realpath(path))
    return any(
        real.is_relative_to(os.path.realpath(home))
        for home in (layout.default_lemons_dir(), layout.default_legacy_dir())
    )


def _parts() -> dict[str, tuple[Path, bool]]:
    """Each part of the storage: where it is, and whether that is away from its default."""
    database = Path(os.environ.get("LEMONAID_DB") or db.default_db_path()).expanduser()
    state = Path(os.environ.get("LEMONAID_STATE_DIR") or default_state_dir()).expanduser()
    briefs, mailboxes = _briefs(), _mailboxes()
    return {
        "the database": (database, not _same(database, db.default_db_path())),
        "the state directory": (state, not _same(state, default_state_dir())),
        "the briefs": (briefs, not _live(briefs)),
        "the mailboxes": (mailboxes, not _live(mailboxes)),
    }


def _listed(parts: list[str]) -> str:
    return parts[0] if len(parts) == 1 else f"{', '.join(parts[:-1])} and {parts[-1]}"


def partial() -> str:
    """Why this run's storage is partly redirected, or "" when all of it or none is."""
    parts = _parts()
    moved = [f"{name} ({path})" for name, (path, redirected) in parts.items() if redirected]
    if not moved or len(moved) == len(parts):
        return ""

    kept = [f"{name} ({path})" for name, (path, redirected) in parts.items() if not redirected]
    return (
        "lemonaid won't run with only part of its storage redirected. "
        f"Redirected: {_listed(moved)}. Not redirected: {_listed(kept)}. Redirect LEMONAID_DB, "
        "LEMONAID_STATE_DIR, LEMONAID_LEMONS_DIR and LEMONAID_LEGACY_BRIEFS_DIR together, "
        "or none of them."
    )
