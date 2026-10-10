"""Whether a message's recipient will read it, judged at send time from what is running now.

A Codex lemon reads whatever the delivery service queues into its thread; a
Claude lemon reads only while its inbox waiter holds the lock, or when the turn
it is in ends and its Stop hook makes it arm one. Neither reads anything once
its harness has exited.
"""

import subprocess
import time
import typing as ty
from pathlib import Path

from .. import handlers
from ..inbox import db, turns
from . import waiter

LISTENING = "listening"
MID_TURN = "mid-turn"
NOT_STARTED = "not started"
UNKNOWN = "unknown"
ASKING = "asking"
DEAF = "deaf"
DEAD = "dead"

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


def harness_alive(row: db.Notification) -> bool | None:
    """Whether a harness still runs on the terminal *row* last reported, or None if unknowable.

    A cmux session can move to a new tty when cmux restarts, so cmux is asked
    where it is now instead.
    """
    if row.switch_source in handlers.PER_SESSION_SOURCES:
        found = handlers.where_sessions_are(
            [(row.switch_source, {**row.metadata, "channel": row.channel})], fresh=True
        ).get(row.channel)
        return None if found is None else bool(found)

    tty = str(row.metadata.get("tty") or "")
    commands = _tty_commands(tty) if tty else None
    if commands is None:
        return False if row.is_archived else None

    return any(is_harness(command) for command in commands)


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

    if channel.startswith("codex:"):
        return State(LISTENING, "the delivery service queues it into its thread")

    if armed:
        return State(LISTENING, "its inbox waiter is armed")

    if turns.mid_turn(row, now):
        return State(MID_TURN, "it will arm its inbox waiter when this turn ends")

    if row.turn_at is not None:  # however old: it may have sat at a permission prompt for hours
        return State(ASKING, "it stopped mid-turn to ask its user something")

    return State(DEAF, "it is idle with no inbox waiter")


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
