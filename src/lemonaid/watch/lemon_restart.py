"""Restarting every waiter one lemon has, the ones it started by hand included.

lemonaid can't start a hand-started waiter again where it ran (a harness task, or a
terminal of its own), so it stops one only once the lemon's running watcher reads the
same source from the brief.
"""

import pathlib
import sqlite3
import time
import typing as ty
from collections import abc

from ..brief import identity, lemon
from ..codex import channels
from ..config import load_config
from ..log import get_logger
from . import (
    codex_waiter,
    push_scout,
    registry,
    scout_roster,
    stopping,
    subscriptions,
    wait_state,
)

_log = get_logger("watch.lemon_restart")

_COMMAND = "lemonaid watch restart"


class Lemon(ty.NamedTuple):
    lemon_id: str
    channel: str  # the session its brief is attached to; "" for none
    brief: pathlib.Path | None


def named(conn: sqlite3.Connection, target: str) -> Lemon:
    """The lemon *target* names: a channel, a Lemon-ID or a brief's name, or a detached lemon's Lemon-ID."""
    try:
        found = lemon.attachment(conn, target)
    except LookupError:
        brief = lemon.brief_of(conn, target) if identity.valid(target) else None
        if brief is None:
            raise

        return Lemon(lemon.current(conn, target), "", brief)

    return Lemon(identity.ensure(conn, found.path), found.channel, found.path)


def _theirs(waiter: registry.Waiter, lemon: Lemon) -> bool:
    return (
        waiter.lemon == lemon.lemon_id
        or (bool(lemon.channel) and waiter.channel == lemon.channel)
        or (waiter.kind == "mailbox" and lemon.lemon_id in waiter.targets)
    )


def hand_started(lemon: Lemon, waiters: abc.Iterable[registry.Waiter]) -> list[registry.Waiter]:
    return [w for w in waiters if w.kind != "wait" and _theirs(w, lemon)]


def every(lemon: Lemon, waiters: abc.Iterable[registry.Waiter]) -> list[registry.Waiter]:
    """All of *lemon*'s waiters: its watcher or push scout, and the ones it started by hand."""
    return [
        w
        for w in waiters
        if (w.kind == "wait" and lemon.lemon_id in w.targets) or _theirs(w, lemon)
    ]


def _key(kind: str, target: abc.Iterable[str]) -> tuple[str, tuple[str, ...]]:
    return kind, tuple(t.lower() if kind in ("pr", "repo") else t for t in target)


def _source(waiter: registry.Waiter) -> tuple[str, tuple[str, ...]]:
    if waiter.kind == "pr":
        repo, _, number = waiter.targets[0].rpartition("#")
        return _key("pr", (repo, number))

    return _key(waiter.kind, waiter.targets)


def followed(text: str, lemon_id: str, cwd: pathlib.Path) -> abc.Callable[[registry.Waiter], bool]:
    """Whether a watcher running in *cwd* that reads the brief *text* watches what a waiter does.

    Relative paths resolve against the watcher's cwd, not the waiter's, and a listed
    command the reader rejects (a PR with no repo, a doc watch list) follows nothing.
    """
    specs = subscriptions.report(
        text, cwd, lemon_id, tuple(load_config().brief.vaults), link_nudge=False
    ).specs
    keys = {_key(spec.kind, spec.target) for spec in specs}
    return lambda waiter: waiter.kind == "mailbox" or _source(waiter) in keys


def _watcher(lemon_id: str, wait: float) -> registry.Waiter | None:
    """The lemon's registered watcher once it is armed, waiting up to *wait* seconds,
    or longer while the scout host restarts."""
    deadline = time.monotonic() + wait
    restart_deadline = time.monotonic() + push_scout.RESTART_WAIT
    while True:
        found = [w for w in registry.running() if w.kind == "wait" and lemon_id in w.targets]
        if found and wait_state.is_armed(lemon_id):
            return found[0]

        now = time.monotonic()
        if now >= deadline and not (now < restart_deadline and scout_roster.restarting()):
            return None

        time.sleep(0.5)


def _follows(lemon: Lemon, watcher: registry.Waiter) -> abc.Callable[[registry.Waiter], bool]:
    try:
        text = lemon.brief.read_text() if lemon.brief else ""
    except OSError as error:
        _log.warning("could not read %s: %s", lemon.brief, error)
        text = ""
    return followed(text, lemon.lemon_id, pathlib.Path(watcher.cwd))


def stop_hand_started(lemon: Lemon, by: str, wait: float) -> abc.Iterator[str]:
    """Stop each waiter *lemon* started by hand that its watcher follows; a line for each.

    The others keep running, since nothing else would watch what they watch.
    """
    found = hand_started(lemon, registry.running())
    if not found:
        return

    watcher = _watcher(lemon.lemon_id, wait)
    follows = _follows(lemon, watcher) if watcher else lambda waiter: False
    for waiter in found:
        what = f"{waiter.kind} waiter ({', '.join(waiter.targets)}), pid {waiter.pid}"
        if not follows(waiter):
            why = "its watcher doesn't follow it" if watcher else "no watcher runs"
            yield f"{lemon.lemon_id}: left its {what}, running: {why}"
            continue

        try:
            stopping.stop(waiter, by, command=_COMMAND, followed=True)
        except TimeoutError as error:
            _log.warning("%s", error)
            yield f"{lemon.lemon_id}: its {what}, did not exit; stop it with `kill {waiter.pid}`"
            continue

        yield f"{lemon.lemon_id}: stopped its {what}; its watcher follows it"


def start_scout(channel: str, lemon_id: str) -> bool | None:
    """Have the scout host push into *channel* for the lemon; None for a channel neither Claude's nor Codex's."""
    if channel.startswith("claude:"):
        return push_scout.ensure(channel.removeprefix("claude:"), lemon_id)

    if channel.startswith("codex:"):
        return codex_waiter.ensure(channel, channels.thread(channel), lemon_id)

    return None


def _why_not(channel: str) -> str:
    if channel.startswith("claude:"):
        session = push_scout.session(channel.removeprefix("claude:"))
        if why := push_scout.problem(session):
            return why

    return f"see {scout_roster.log_path()}"


def start_watcher(lemon: Lemon) -> str:
    if not lemon.channel:
        return (
            f"{lemon.lemon_id}: its brief is attached to no session, so no push scout was started"
        )

    started = start_scout(lemon.channel, lemon.lemon_id)
    if started:
        return f"{lemon.lemon_id}: started its push scout"

    why = (
        "only Claude and Codex lemons have push scouts"
        if started is None
        else _why_not(lemon.channel)
    )
    return f"{lemon.lemon_id}: could not start a push scout ({why}); its lemon must rearm `lemonaid watch --self`"
