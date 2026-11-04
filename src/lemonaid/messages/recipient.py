"""Whether a message's recipient will read it, judged at send time from what is running now.

A Codex lemon reads queued messages while its mailbox waiter holds the lock, or
from its active turn; a Claude lemon reads while its mailbox waiter holds the
lock, or when its turn ends and its Stop hook makes it arm one. Neither reads
anything once its harness has exited. A Claude lemon reads nothing while
Claude Code has parked its conversation in a background job, and a Codex lemon
reads nothing that Codex holds in its queue and starts no turn from.
"""

import subprocess
import time
import typing as ty
from collections import abc
from pathlib import Path

from .. import handlers
from ..claude import session_socket
from ..codex import channels as codex_channels
from ..codex import daemon_setup, processes, queued
from ..codex import utils as codex_utils
from ..inbox import db, turns
from ..inbox.channel import channel_id
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
PARKED = "parked"  # a background job runs its Claude conversation, or Codex holds its messages

UNREAD = frozenset({ASKING, DEAF, DEAD, PARKED})

_HARNESSES = ("claude", "codex")
_LISTED_WITHIN = 15.0  # a Codex process listing this recent serves


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


def parked_jobs() -> dict[str, str]:
    """The background job of each parked Claude lemon, by channel."""
    return {
        channel_id("claude", entry.session_id): entry.parked_job
        for entry in session_socket.live()
        if entry.parked_job and entry.session_id
    }


def unrun_codex() -> dict[str, str]:
    """Why each Codex lemon will not read what Codex holds in its queue, by channel.

    Only a thread that a Codex process has open counts. No process runs one that none
    has open, so it is `dead`, and resuming it starts its turns.
    """
    now = time.time()
    reasons = {
        thread: reason
        for thread, found in queued.held(daemon_setup.codex_home()).items()
        if (rollout := codex_utils.find_session_path(thread))
        and (reason := queued.unrun(found, queued.last_turn_end(rollout), now))
    }
    open_threads = processes.open_threads(_LISTED_WITHIN) if reasons else None
    if not open_threads:
        return {}

    with db.connect() as conn:
        return {
            codex_channels.for_session(conn, thread): reason
            for thread, reason in reasons.items()
            if thread in open_threads
        }


def classify(
    channel: str,
    row: db.Notification | None,
    alive: bool | None,
    armed: bool,
    now: float,
    parked: str = "",
    unrun: str = "",
) -> State:
    """The recipient's state, from facts already gathered.

    *alive* is None when the terminal can't be checked; *armed* is whether a
    waiter holds the recipient's mailbox lock; *parked* is the background job
    holding its conversation (see `parked_jobs`), and *unrun* why Codex starts
    no turn from the messages it holds for it (see `unrun_codex`). A parked
    lemon's scout may still hold the lock for a moment, and a Codex lemon's
    scout holds it while Codex holds its messages, so both outrank *armed*.
    *unrun* also outranks the row's turn: Codex's rollout says no turn is open.
    """
    if not channel:
        return State(NOT_STARTED, "it reads its mailbox when it starts")

    if not channel.startswith(("claude:", "codex:")):
        return State(UNKNOWN, "lemonaid can't tell whether this harness reads its mailbox")

    if row is None or alive is False:
        return State(DEAD, "its harness is not running")

    if parked:
        return State(PARKED, session_socket.parked_reason(parked))

    if unrun:
        return State(PARKED, unrun)

    if turns.mid_turn(row, now):
        detail = (
            "the delivery service queues messages into its thread"
            if channel.startswith("codex:")
            else "it reads its mailbox when this turn ends"
        )
        return State(MID_TURN, detail)

    if row.turn_at is not None:  # however old: it may have sat at a permission prompt for hours
        return State(ASKING, "it stopped mid-turn to ask its user something")

    if armed:
        return State(LISTENING, "its mailbox waiter is armed")

    detail = (
        "it is idle with no mailbox waiter to start a turn from queued messages"
        if channel.startswith("codex:")
        else "it is idle with no mailbox waiter"
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


def probe(channel: str, row: db.Notification | None, mailbox: Path) -> State:
    if not channel:
        return classify(channel, row, None, False, time.time())

    return classify(
        channel,
        row,
        harness_alive(row) if row is not None else False,
        waiter.is_armed(mailbox),
        time.time(),
        parked_jobs().get(channel, "") if channel.startswith("claude:") else "",
        unrun_codex().get(channel, "") if channel.startswith("codex:") else "",
    )


def describe(lemon_id: str, found: State) -> str:
    return f"queued for {lemon_id}: {found.state}, {found.detail}"
