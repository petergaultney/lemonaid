"""Choose the inbox row representing each focused terminal."""

import subprocess
import time
from collections.abc import Iterable, Sequence

from ...lemon_watchers import get_tmux_socket
from ...tmux import navigation
from .. import db, sections


def pane_receives_keys(pane: str) -> bool | None:
    """Whether this pane is selected in a visible, attached tmux window."""
    try:
        result = subprocess.run(
            [
                "tmux",
                "display-message",
                "-p",
                "-t",
                pane,
                "#{pane_active} #{window_active} #{session_attached}",
            ],
            capture_output=True,
            text=True,
            timeout=0.3,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    parts = result.stdout.split()
    if len(parts) != 3 or any(not part.isdecimal() for part in parts):
        return None
    return parts[0] == "1" and parts[1] == "1" and int(parts[2]) > 0


FOCUS_CACHE_SECONDS = 1.0
INPUT_CACHE_SECONDS = 0.5


class Probe:
    """What tmux says has the user's attention, asked no more often than it can change.

    A refresh runs on the poll interval and again on every action that
    changes the list - far more often than a pane can be switched by hand,
    and each answer costs a subprocess.
    """

    def __init__(self) -> None:
        self.focused: frozenset[str] = frozenset()
        self.focused_at = 0.0
        self.input_at = 0.0

    def ttys(self) -> frozenset[str]:
        """The ttys of the panes the user is looking at."""
        now = time.time()
        if now - self.focused_at >= FOCUS_CACHE_SECONDS:
            self.focused = frozenset(navigation.focused_ttys(get_tmux_socket()))
            self.focused_at = now

        return self.focused

    def note(self, tty: str) -> None:
        """We just switched to *tty*, ahead of tmux's next answer."""
        self.focused = frozenset({tty})
        self.focused_at = time.time()

    def has_keys(self, pane: str) -> bool | None:
        """Whether *pane* has the keyboard, or None when not asked again yet or unknown."""
        now = time.monotonic()
        if now - self.input_at < INPUT_CACHE_SECONDS:
            return None

        self.input_at = now
        return pane_receives_keys(pane)


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


def is_behind_scratch(notification: db.Notification | None, pane: str) -> bool:
    """Whether *notification* is the session in the terminal this scratch pane covers."""
    behind = behind_scratch(pane, get_tmux_socket())
    return bool(notification and behind and notification.metadata.get("tty") == behind)


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


def first_row(
    entries: Sequence[sections.Header | sections.Row], channels: frozenset[str]
) -> int | None:
    """The index of the first drawn row of one of *channels*, if any is drawn."""
    return next(
        (
            i
            for i, entry in enumerate(entries)
            if isinstance(entry, sections.Row) and entry.notification.channel in channels
        ),
        None,
    )
