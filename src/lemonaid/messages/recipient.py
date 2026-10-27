"""Whether a message's recipient will read it, judged at send time from what is running now.

A Codex lemon reads queued messages while its inbox waiter holds the lock, or
from its active turn; a Claude lemon reads while its inbox waiter holds the
lock, or when its turn ends and its Stop hook makes it arm one. Neither reads
anything once its harness has exited.
"""

import subprocess
import time
import typing as ty
from collections import abc
from pathlib import Path

from .. import handlers
from ..inbox import db, turns
from ..lemon_watchers import owners
from . import waiter

LISTENING = "listening"
MID_TURN = "mid-turn"
NOT_STARTED = "not started"
UNKNOWN = "unknown"
ASKING = "asking"
DEAF = "deaf"
DEAD = "dead"
MOVED = "moved"  # its harness runs, but not on the terminal its row records

UNREAD = frozenset({ASKING, DEAF, DEAD})

_HARNESSES = ("claude", "codex")


class State(ty.NamedTuple):
    state: str
    detail: str


def is_harness(command: str) -> bool:
    """Claude Code may title itself with its version number rather than its name."""
    name = Path(command).name
    return name in _HARNESSES or (name.replace(".", "").isdigit() and "." in name)


def _tty_commands(tty: str) -> list[str] | None:
    """The command of every process on *tty*, or None if `ps` could not say."""
    try:
        result = subprocess.run(
            ["ps", "-t", tty.removeprefix("/dev/"), "-o", "comm="],
            capture_output=True,
            text=True,
        )
    except OSError:
        return None

    if result.returncode != 0 and (result.returncode != 1 or result.stderr.strip()):
        # `ps` also exits 1, with a message, for a tty it can't look at; only a
        # missing device says the terminal is gone.
        return None if Path("/dev", tty.removeprefix("/dev/")).exists() else []

    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _every_tty() -> dict[str, list[str]] | None:
    """The command of every process on each tty, from one `ps`, or None if it could not say."""
    try:
        result = subprocess.run(["ps", "-A", "-o", "tty=,comm="], capture_output=True, text=True)
    except OSError:
        return None

    if result.returncode != 0:
        return None

    found: dict[str, list[str]] = {}
    for line in result.stdout.splitlines():
        tty, _, command = line.strip().partition(" ")
        if tty and command.strip():
            found.setdefault(tty, []).append(command.strip())
    return found


def tty_commands() -> abc.Callable[[str], list[str] | None]:
    """`_tty_commands` for many ttys, from one `ps` for all of them where it can."""
    every = _every_tty()
    if every is None:
        return lambda tty: _tty_commands(tty)

    def commands(tty: str) -> list[str] | None:
        name = tty.removeprefix("/dev/")
        if name in every:
            return every[name]

        return _tty_commands(tty) if Path("/dev", name).exists() else []

    return commands


def harness_alive(
    row: db.Notification, commands: abc.Callable[[str], list[str] | None] | None = None
) -> bool | None:
    """Whether a harness still runs on the terminal *row* last reported, or None if unknowable.

    A cmux session can move to a new tty when cmux restarts, so cmux is asked
    where it is now instead. *commands* stands in for `ps` (see `tty_commands`).
    """
    if row.switch_source in handlers.PER_SESSION_SOURCES:
        found = handlers.where_sessions_are(
            [(row.switch_source, {**row.metadata, "channel": row.channel})], fresh=True
        ).get(row.channel)
        return None if found is None else bool(found)

    tty = str(row.metadata.get("tty") or "")
    running = (commands or _tty_commands)(tty) if tty else None
    if running is None:
        return False if row.is_archived else None

    return any(is_harness(command) for command in running)


def classify(
    channel: str, row: db.Notification | None, alive: bool | None, armed: bool, now: float
) -> State:
    """The recipient's state, from facts already gathered.

    *alive* is None when the terminal can't be checked; *armed* is whether a
    waiter holds the recipient's inbox lock.
    """
    if not channel:
        return State(NOT_STARTED, "it reads its inbox when it starts")

    if not channel.startswith(("claude:", "codex:")):
        return State(UNKNOWN, "lemonaid can't tell whether this harness reads its inbox")

    if row is None or alive is False:
        return State(DEAD, "its harness is not running")

    if turns.mid_turn(row, now):
        detail = (
            "the delivery service queues messages into its thread"
            if channel.startswith("codex:")
            else "it reads its inbox when this turn ends"
        )
        return State(MID_TURN, detail)

    if row.turn_at is not None:  # however old: it may have sat at a permission prompt for hours
        return State(ASKING, "it stopped mid-turn to ask its user something")

    if armed:
        return State(LISTENING, "its inbox waiter is armed")

    detail = (
        "it is idle with no inbox waiter to start a turn from queued messages"
        if channel.startswith("codex:")
        else "it is idle with no inbox waiter"
    )
    return State(DEAF, detail)


def confirmed(row: db.Notification, state: State) -> State:
    """*state*, checked against the lemon's own process before acting on it.

    `harness_alive` judges by the row's tty, and ttys are reused: a lemon called
    deaf may have exited with another lemon now on its terminal, and one called
    dead may be running on a terminal its row doesn't record yet.
    """
    if state.state not in (DEAF, DEAD):
        return state

    running = owners.running()
    if running is None:
        return state

    where = owners.ttys(row, running)
    if not where:
        return State(DEAD, "its harness is not running") if state.state == DEAF else state

    if row.metadata.get("tty") not in where:
        return State(
            MOVED, f"it runs on {', '.join(sorted(where))}, not the terminal its row records"
        )

    return state


def probe(channel: str, row: db.Notification | None, inbox: Path) -> State:
    if not channel:
        return classify(channel, row, None, False, time.time())

    return classify(
        channel,
        row,
        harness_alive(row) if row is not None else False,
        waiter.is_armed(inbox),
        time.time(),
    )


def describe(lemon_id: str, found: State) -> str:
    return f"queued for {lemon_id}: {found.state}, {found.detail}"
