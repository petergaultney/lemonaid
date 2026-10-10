"""What lemonaid can see about one lemon, without judging it.

Each fact comes from a cheap local check and can mislead in a known way (see
docs/for-lemons.md). Deciding what they add up to is left to the reader.
"""

import dataclasses
import re
import time
from pathlib import Path

from ..brief import attached, status
from ..inbox import db
from ..launch import window
from ..log import get_logger
from ..messages import autoresume_tmux, recipient, resume_log, store, waiter
from ..watch import registry

_log = get_logger("lemon_facts")

_WAITERS = re.compile(r"##\s+waiters\s*", re.IGNORECASE)
_COMMAND = re.compile(r"``\s*(.+?)\s*``|`([^`]+)`")  # double ticks hold a command with ticks in it


@dataclasses.dataclass(frozen=True)
class Facts:
    lemon_id: str
    channel: str
    brief: str
    status: str  # the brief's Status word, or ""
    parent: str  # its parent's Lemon-ID, or ""
    archived: bool
    snoozed: bool
    state: str  # as `tell` would report it: listening, mid-turn, asking, deaf, dead, ...
    state_detail: str
    harness_running: bool | None  # None: the terminal couldn't be checked
    inbox_waiter: bool
    pane: str | None  # "empty prompt", "dialog: <what>", "other"; None outside tmux or when gone
    waiters_listed: list[str]
    waiters_running: list[str]
    messages_queued: int
    exited_at: float | None  # from the SessionEnd hook; cleared by the session's next hook
    exit_reason: str
    last_activity: float | None  # the transcript's last write
    recent_starts: int  # autoresume and `lemon resume` starts within the limit's window


def _listed_waiters(text: str) -> list[str]:
    """The commands in the brief's `## Waiters` bullets."""
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if _WAITERS.fullmatch(line)), None)
    if start is None:
        return []

    found = []
    for line in lines[start + 1 :]:
        if line.startswith("#"):
            break
        if line.startswith("- ") and (command := _COMMAND.search(line)):
            found.append(command.group(1) or command.group(2))
    return found


def _pane(row: db.Notification, alive: bool | None) -> str | None:
    terminal = row.switch_source or ("tmux" if row.metadata.get("tmux_session") else "")
    if not alive or terminal != "tmux":
        return None

    screen = autoresume_tmux.screen(row)
    if screen is None:
        return None

    if dialog := window.dialog_in(screen):
        return f"dialog: {dialog}"

    return "empty prompt" if autoresume_tmux.ready_for_input(screen) else "other"


def _mtime(path: str) -> float | None:
    try:
        return Path(path).stat().st_mtime if path else None
    except OSError:
        return None


def _text(path: Path) -> str:
    try:
        return path.read_text()
    except OSError as error:
        _log.warning("Could not read brief %s: %s", path, error)
        return ""


def gather(found: attached.Attachment, lemon_id: str, parent: str, window: float) -> Facts:
    """The facts about *found*'s lemon; *window* is the start limit's, in seconds."""
    row, inbox, text = found.notification, store.inbox_for_id(lemon_id), _text(found.path)
    alive = recipient.harness_alive(row) if row is not None else False
    armed = waiter.is_armed(inbox)
    state = recipient.classify(found.channel, row, alive, armed, time.time())
    metadata = row.metadata if row is not None else {}
    return Facts(
        lemon_id=lemon_id,
        channel=found.channel,
        brief=str(found.path),
        status=status.split(text).status,
        parent=parent,
        archived=bool(row and row.is_archived),
        snoozed=bool(row and row.is_snoozed),
        state=state.state,
        state_detail=state.detail,
        harness_running=alive,
        inbox_waiter=armed,
        pane=_pane(row, alive) if row is not None else None,
        waiters_listed=_listed_waiters(text),
        waiters_running=[w.command for w in registry.mine(found.channel)],
        messages_queued=store.pending_count(inbox),
        exited_at=metadata.get("exited_at"),
        exit_reason=str(metadata.get("exit_reason") or ""),
        last_activity=_mtime(str(metadata.get("transcript_path") or "")),
        recent_starts=resume_log.within(resume_log.entries(inbox), time.time(), window),
    )
