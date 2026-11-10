"""After a lost lemon runs again: its brief, its subscriptions, and only the prompts it needs.

A lemon whose push scout runs gets its subscriptions back with no turn started in
it. Only a lemon that can't be pushed to is prompted, and then only when its brief
lists waiters or processes of its died with the terminal.
"""

import sqlite3
import time
from collections import abc

from ..brief import attached
from ..codex import channels
from ..config import Config
from ..inbox import db
from ..messages import store
from ..watch import codex_waiter, push_path, push_scout, wait_state
from . import report, run

Prompt = abc.Callable[[db.Notification, Config, str], str]  # types into the lemon; why not, or ""


def _subscribed(lemon: run.Lemon, row: db.Notification) -> bool:
    """Whether its watch events reach the lemon without a prompt, starting its scout if none runs.

    A Claude scout can outlive the terminal, so one that runs is not enough: the
    resumed session must take what it pushes.
    """
    harness = row.channel.partition(":")[0]
    if harness == "claude" and (session := str(row.metadata.get("session_id") or "")):
        push_scout.ensure(session, lemon.lemon_id)
        found = push_path.gather(lemon.lemon_id, session)
        return found.scout and not push_path.path_of(found).loud

    if harness == "codex" and (thread := channels.owner_id(row.channel, row.metadata, {})):
        codex_waiter.ensure(row.channel, thread, lemon.lemon_id)

    return wait_state.is_armed(lemon.lemon_id)


_READY_SECONDS = 30.0  # for a harness proven running to show its empty composer
_READY_POLL = 0.5


def _typed(attempt: abc.Callable[[], str]) -> str:
    """Type the prompt once the harness can take it: why not, or "".

    A harness runs before it draws its composer, and typing refuses a pane without an
    empty one, so a refusal is retried until the composer shows or time runs out.
    """
    deadline = time.monotonic() + _READY_SECONDS
    while (why := attempt()) and time.monotonic() < deadline:
        time.sleep(_READY_POLL)
    return why


def _result(lemon: run.Lemon, where: str, outcome: str, detail: str = "") -> report.Result:
    return report.Result(lemon.channel, lemon.row.name or lemon.channel, where, outcome, detail)


def settle(
    conn: sqlite3.Connection,
    lemon: run.Lemon,
    where: str,
    config: Config,
    prompt: Prompt,
) -> report.Placed | report.Result:
    """Check *lemon*'s brief, bring its subscriptions back, and tell it what it must know.

    A Placed lemon still has to be heard from (see `report.wait`); a Result is final.
    """
    row = db.get_by_channel(conn, lemon.channel, unread_only=False) or lemon.row
    placed = report.Placed(lemon.channel, row.name or lemon.channel, where, report.NO_BRIEF)
    if not lemon.lemon_id:
        return placed

    if lemon.channel not in attached.by_channel(conn, [lemon.channel]):
        return _result(lemon, where, report.DETACHED, "its brief is no longer attached to it")

    subscribed = _subscribed(lemon, row)
    if lemon.note:
        store.send(store.mailbox_for_id(lemon.lemon_id), lemon.note, "lemonaid restore")
    if subscribed:
        return placed._replace(rearm=report.SUBSCRIBED)

    text = " ".join(part for part in (lemon.rearm, lemon.note) if part)
    if not text:
        return placed._replace(rearm=report.NOTHING_TO_REARM)

    if not lemon.launch.promptable:
        return placed._replace(rearm=report.BY_HAND)

    if why := _typed(lambda: prompt(row, config, text)):
        return _result(lemon, where, report.BY_HAND, why)

    return placed._replace(rearm=report.PROMPTED)


def settle_all(
    conn: sqlite3.Connection,
    lemons: abc.Iterable[run.Lemon],
    where: abc.Callable[[run.Lemon], str],
    config: Config,
    prompt: Prompt,
) -> tuple[list[report.Placed], list[report.Result]]:
    settled = [settle(conn, lemon, where(lemon), config, prompt) for lemon in lemons]
    return (
        [s for s in settled if isinstance(s, report.Placed)],
        [s for s in settled if isinstance(s, report.Result)],
    )
