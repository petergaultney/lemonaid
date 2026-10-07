"""Choose the inbox row representing each focused terminal."""

import subprocess
from collections.abc import Iterable

from ...tmux import navigation
from .. import db


def behind_scratch(pane: str, socket: str | None) -> str | None:
    """The terminal behind this scratch pane, rather than another client's pane."""
    try:
        result = subprocess.run(
            [
                *navigation.server_args(socket),
                "list-panes",
                "-t",
                pane,
                "-F",
                "#{pane_tty}|#{pane_last}|#{@lemonaid_scratch}",
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=0.5,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    for line in result.stdout.splitlines():
        parts = line.split("|")
        if len(parts) == 3 and parts[1] == "1" and parts[2] != "1":
            return parts[0]
    return None


def channels(rows: Iterable[db.Notification], ttys: frozenset[str]) -> frozenset[str]:
    """A terminal's latest notification owns its marker.

    Older channels can retain the same tty after another lemon takes over that
    terminal. They remain useful inbox rows, but are not additional focused panes.
    Choose before filtering or folding, so hiding the current row cannot make an
    older one look current instead.
    """
    latest: dict[str, db.Notification] = {}
    for row in rows:
        tty = row.metadata.get("tty")
        if tty not in ttys:
            continue
        previous = latest.get(tty)
        if previous is None or (row.created_at, row.id) > (previous.created_at, previous.id):
            latest[tty] = row

    return frozenset(row.channel for row in latest.values())
