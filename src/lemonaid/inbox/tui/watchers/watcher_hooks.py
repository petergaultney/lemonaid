"""The inbox's side of the transcript watcher: what it reads and records in the database."""

import functools
import sqlite3
import time
import typing as ty
from collections import abc

from .... import claude, codex, config, handlers, openclaw, opencode, status_registry
from ....audit import events
from ....brief import attached
from ....brief import status as brief_status
from ....claude import live_sessions
from ....config import Config
from ....hooks import end_reports
from ....lemon_watchers import ModelInfo, start_unified_watcher, tty_processes, watcher
from ....restore import auto, front_ends, loss, readiness
from ....watch import codex_waiter
from ... import db, ended, teardown_evidence
from ..rows import brief_cards

_ActiveRow = tuple[str, str, str, float, bool, str | None, str, str | None]
_SessionOrder = tuple[int, int, int]  # tmux.navigation.SessionOrder, without importing tmux
_LOSS_SECONDS = 30.0  # between checks for lemons lost with their terminal server
_READY_SECONDS = 60.0  # between checks of which running lemons a restore would miss


def active_sessions() -> list[_ActiveRow]:
    """Every live session with a session ID and directory, switchable or not.

    Stale cleanup archives dead sessions regardless of where they can be switched from.
    Each is (channel, session_id, cwd, created_at, is_unread, tty, message, switch_source).
    A lemon lost with its terminal server, or whose harness crashed, is left out: nothing
    about its pane or tty says anything about it now, and restore needs its row as it is.
    """
    with db.connect() as conn:
        notifications = db.get_active(conn, switch_source=None)

    return [
        (
            n.channel,
            n.metadata["session_id"],
            n.metadata["cwd"],
            n.created_at,
            n.is_unread,
            n.metadata.get("tty"),
            n.message,
            n.switch_source,
        )
        for n in notifications
        if n.metadata.get("session_id")
        and n.metadata.get("cwd")
        and not ended.revivable(n.metadata)
    ]


def mark_channel_read(channel: str) -> int:
    with db.connect() as conn:
        return db.mark_all_read_for_channel(conn, channel)


def mark_channel_unread(channel: str) -> int:
    with db.connect() as conn:
        return db.mark_unread_for_channel(conn, channel)


def mark_channel_read_after_turn(channel: str) -> int:
    with db.connect() as conn:
        return db.mark_read_after_turn(conn, channel)


def record_channel_turn(channel: str, at: float | None) -> None:
    with db.connect() as conn:
        db.record_turn(conn, channel, at)


def update_channel_message(channel: str, message: str) -> int:
    with db.connect() as conn:
        return db.update_message(conn, channel, message)


def recorded_sockets() -> dict[str, str]:
    """Which tmux server each active session was last seen on.

    The watcher asks tmux whether a pane is still there, and a pane on
    another server is absent from this one's listing for reasons that have
    nothing to do with the session being alive.
    """
    with db.connect() as conn:
        return {
            n.channel: socket
            for n in db.get_active(conn, switch_source="tmux")
            if (socket := n.metadata.get("tmux_socket"))
        }


def recorded_tmux_session_orders() -> dict[str, _SessionOrder]:
    """Each active channel's tmux identity, if recorded by its own hook."""
    with db.connect() as conn:
        orders: dict[str, _SessionOrder] = {}
        for notification in db.get_active(conn, switch_source="tmux"):
            value = notification.metadata.get("tmux_session_order")
            if (
                isinstance(value, list)
                and len(value) == 3
                and all(isinstance(part, int) for part in value)
            ):
                orders[notification.channel] = (value[0], value[1], value[2])
        return orders


def recorded_tmux_pane_ids() -> dict[str, str]:
    """Each active channel's recorded tmux pane id, if its own hook recorded one."""
    with db.connect() as conn:
        return {
            n.channel: value[0]
            for n in db.get_active(conn, switch_source="tmux")
            if isinstance(value := n.metadata.get("tmux_pane_identity"), list)
            and value
            and isinstance(value[0], str)
        }


def protected_brief_channels(brief_cache: brief_cards.BriefCache) -> set[str]:
    """Channels whose attached brief is waiting for a person to act."""
    with db.connect() as conn:
        channels = [
            n.channel
            for n in db.get_active(conn, switch_source=None)
            if not teardown_evidence.applies(n)
        ]
        paths = attached.by_channel(conn, channels)
    return {
        channel
        for channel, path in paths.items()
        if (card := brief_cache.get(path)) is not None
        and card.status in status_registry.yours(config.brief_statuses())
    }


def locate_sessions(active: list[tuple]) -> dict[str, str | ty.Literal[False] | None]:
    """Where each active session that can outlive its tty runs now (see handlers)."""
    channels = {row[0] for row in active if row[7] in handlers.PER_SESSION_SOURCES}
    if not channels:
        return {}

    with db.connect() as conn:
        sessions = [
            (n.switch_source, {**n.metadata, "channel": n.channel})
            for n in db.get_active(conn, switch_source=None)
            if n.channel in channels
        ]
    return handlers.where_sessions_are(sessions)


def recorded_models() -> dict[str, ModelInfo]:
    with db.connect() as conn:
        return {
            n.channel: ModelInfo(provider, model)
            for n in db.get_active(conn, switch_source=None)
            if isinstance((provider := n.metadata.get("model_provider")), str)
            and isinstance((model := n.metadata.get("model")), str)
            and model
        }


def record_channel_location(
    channel: str,
    session: str,
    window: str,
    socket: str | None = None,
    session_order: _SessionOrder | None = None,
) -> None:
    """Note where a session is sitting, so `tmux restore` can rebuild it.

    Done on the watcher's poll rather than only when a session notifies:
    an idle session would otherwise never record one, and those are the
    ones whose position is hardest to remember after a crash.
    """
    with db.connect() as conn:
        db.record_location(conn, channel, session, window, socket, session_order)


def record_channel_model(channel: str, provider: str, model: str) -> None:
    with db.connect() as conn:
        db.record_model(conn, channel, provider, model)


def record_channel_context(channel: str, used: int, window: int) -> None:
    with db.connect() as conn:
        db.record_context(conn, channel, used, window)


# The watcher's archive reasons, by the end cause each records.
_CAUSES = {
    "pane-gone": ended.PANE_CLOSED,
    "process-exited": ended.PROCESS_EXITED,
    "no-codex-in-cwd": ended.PROCESS_EXITED,
    "replaced-on-tty": ended.REPLACED,
}


def _brief_done(conn: sqlite3.Connection, channel: str) -> bool:
    path = attached.by_channel(conn, [channel]).get(channel)

    return (
        path is not None
        and path.is_file()
        and brief_status.split(path.read_text()).status == "done"
    )


def _crashed(conn: sqlite3.Connection, row: db.Notification | None, why: str) -> bool:
    """Whether the newest lemon on its tty stopped while its pane lives, without the quit
    report its harness gives (only a harness that reports quits counts). A lemon whose
    brief says `done` finished its work, so there is nothing for restore to bring back."""
    return (
        row is not None
        and not _brief_done(conn, row.channel)
        and why.split(" ", 1)[0] == "process-exited"
        and not ended.reported(row.metadata)
        and not db.newer_on_tty(conn, row)
        and end_reports.reported(row.channel.partition(":")[0], row.metadata.get("cwd") or "")
    )


def archive_channel(channel: str, why: str) -> None:
    """Archive all notifications for a channel whose session exited, and audit it.

    A lemon whose server is gone is marked lost instead, and one whose harness crashed
    is marked crashed. A harness that reported its own end (`exit_reason`) ended by the
    user's hand, whatever the watcher then saw.
    """
    with db.connect() as conn:
        row = db.get_by_channel(conn, channel, unread_only=False)
        gone = loss.gone_with_server(conn, row, by="inbox watcher") if row is not None else ""
        if gone == ended.SERVER_LOST:
            events.record("inbox-lost", channel, row.metadata.get("tty", ""), by="inbox watcher")
            return

        if gone:
            events.record("inbox-archive", channel, why, by="inbox watcher")
            return

        if _crashed(conn, row, why):
            db.mark_crashed(conn, channel, "inbox watcher", why)
            events.record("inbox-crashed", channel, why, by="inbox watcher")
            return

        cause = (row is not None and ended.reported(row.metadata)) or _CAUSES.get(
            why.split(" ", 1)[0], ended.PROCESS_EXITED
        )
        db.archive_channel(conn, channel, why, cause=cause, by="inbox watcher")
    events.record("inbox-archive", channel, why, by="inbox watcher")


def start(
    config: Config,
    brief_cache: brief_cards.BriefCache,
    detached_channels: abc.Callable[[set[str]], None],
) -> None:
    last_repair: float | None = None
    last_loss: float | None = None  # the first pass looks for lemons lost before the inbox started
    last_ready: float | None = None  # the first check waits for locations to be recorded
    was_up = True  # whether a terminal to restore into ran at the last loss check
    harness_ttys = tty_processes.Reused(
        lambda args: any(
            watcher.is_harness(args, name) for name in ("claude", "codex", "openclaw", "opencode")
        )
    )

    def active() -> list[tuple]:
        nonlocal last_repair, last_loss, last_ready, was_up
        now = time.monotonic()
        if last_repair is None or now - last_repair >= 10:
            last_repair = now
            locations = handlers.codex_tmux_locations()
            if locations is not None:
                with db.connect() as conn:
                    handlers.repair_tmux_locations(conn, locations)
                    codex_waiter.restore(
                        conn,
                        {
                            thread: {match["tty"] for match in matches}
                            for thread, matches in locations.items()
                        },
                    )
        if last_loss is None or now - last_loss >= _LOSS_SECONDS:
            first = last_loss is None
            last_loss = now
            up = any(terminal.up() for terminal in front_ends.restorers())
            came_up, was_up = up and not was_up, up
            with db.connect() as conn:
                newly = loss.mark(conn, by="inbox watcher")
                for row in newly:
                    events.record(
                        "inbox-lost", row.channel, row.metadata.get("tty", ""), by="inbox watcher"
                    )
                if auto.due(conn, config.restore.auto, bool(newly) or first or came_up):
                    auto.trigger()
        if last_ready is None:
            last_ready = now
        elif now - last_ready >= _READY_SECONDS:
            last_ready = now
            with db.connect() as conn:
                readiness.check(conn, config)
        return active_sessions()

    start_unified_watcher(
        backends=ty.cast(list, [claude.watcher, codex.watcher, openclaw.watcher, opencode.watcher]),
        get_active=active,
        mark_read=mark_channel_read,
        update_message=update_channel_message,
        archive_channel=archive_channel,
        mark_unread=mark_channel_unread,
        record_location=record_channel_location,
        record_model=record_channel_model,
        record_context=record_channel_context,
        models=recorded_models,
        sockets=recorded_sockets,
        session_orders=recorded_tmux_session_orders,
        pane_ids=recorded_tmux_pane_ids,
        locate_sessions=locate_sessions,
        auto_read_patterns=config.inbox.auto_read,
        mark_read_after_turn=mark_channel_read_after_turn,
        record_turn=record_channel_turn,
        protected_channels=functools.partial(protected_brief_channels, brief_cache),
        detached_channels=detached_channels,
        tty_processes=lambda fresh: harness_ttys.by_tty(fresh, time.time()),
        claude_sessions=live_sessions.by_tty,
    )
