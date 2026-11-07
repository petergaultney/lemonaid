"""Audit an edit made to a brief by anyone but the lemon it belongs to."""

from pathlib import Path

from ..audit import events
from . import identity


def record(path: Path, editor: str) -> None:
    """*editor* is the name half of the editing lemon's Brief-ID, "" when it has none."""
    try:
        lemon_id = identity.from_path(path)
    except (OSError, ValueError):
        lemon_id = ""
    if editor and identity.brief_name(lemon_id) == editor:
        return

    events.record("brief-edit", lemon_id or path.name, brief=str(path))
