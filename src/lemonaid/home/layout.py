"""Where briefs and messages live: `~/.lemons/`, or the older `~/.brief-lemons/`.

The new home becomes the active one only when `lemonaid home migrate` writes its
cutover marker, or when there was never an old home to move. Until then
everything reads and writes the old home, whatever else exists in the new one.
While a migration is in progress, brief and message commands refuse.
"""

import os
from pathlib import Path

CUTOVER = "cutover"
MIGRATING = ".migrating"


def lemons_dir() -> Path:
    override = os.environ.get("LEMONAID_LEMONS_DIR")
    return Path(override) if override else Path.home() / ".lemons"


def legacy_dir() -> Path:
    override = os.environ.get("LEMONAID_LEGACY_BRIEFS_DIR")
    return Path(override) if override else Path.home() / ".brief-lemons"


def cut_over() -> bool:
    if (lemons_dir() / CUTOVER).exists():
        return True

    return not legacy_dir().exists() and not (lemons_dir() / MIGRATING).exists()


def briefs_dir() -> Path:
    return lemons_dir() / "brief" if cut_over() else legacy_dir()


def inbox_root() -> Path:
    return lemons_dir() / "inbox" if cut_over() else legacy_dir() / "inbox"


def stray() -> str:
    """Why the old home must be reconciled first, or "" when it needn't.

    Once cut over, anything written to `~/.brief-lemons/` - an editor's save, an
    older lemonaid - is outside the active home, so it stops brief and message
    commands until `home migrate --reconcile` brings it in.
    """
    if not (lemons_dir() / CUTOVER).exists():
        return ""

    if legacy_dir().exists() or legacy_dir().is_symlink():
        return (
            f"{legacy_dir()} exists again after the migration to {lemons_dir()}; brief and "
            "message commands wait until `lemonaid home migrate --reconcile` moves it in"
        )

    return ""


def paused() -> str:
    """Why brief and message commands must wait, or "" when they needn't."""
    if (lemons_dir() / MIGRATING).exists():
        return (
            f"A lemonaid home migration is in progress ({lemons_dir() / MIGRATING}); "
            "brief and message commands wait until `lemonaid home migrate` finishes"
        )

    return stray()
