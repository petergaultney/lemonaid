"""The inbox's side of the transcript watcher: what it reads and records in the database."""

import functools
import time
import typing as ty
from collections import abc

from .... import claude, codex, handlers, openclaw, opencode
from ....brief import attached
from ....config import Config
from ....lemon_watchers import ModelInfo, start_unified_watcher, tty_processes
from ....watch import codex_waiter
from ... import db, teardown_evidence
from ..rows import brief_cards

_ActiveRow = tuple[str, str, str, float, bool, str | None, str, str | None]
_SessionOrder = tuple[int, int, int]  # tmux.navigation.SessionOrder, without importing tmux


def active_sessions() -> list[_ActiveRow]:
    """Every live session with a session ID and directory, switchable or not.

    Stale cleanup archives dead sessions regardless of where they can be switched from.
    Each is (channel, session_id, cwd, created_at, is_unread, tty, message, switch_source).
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
        if n.metadata.get("session_id") and n.metadata.get("cwd")
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
        and card.status in {"merge", "approve", "blocked", "alert"}
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


def archive_channel(channel: str) -> None:
    """Archive all notifications for a channel (session exited)."""
    with db.connect() as conn:
        db.archive_channel(conn, channel, "watcher-stale-session")


def start(
    config: Config,
    brief_cache: brief_cards.BriefCache,
    detached_channels: abc.Callable[[set[str]], None],
) -> None:
    last_repair: float | None = None

    def active() -> list[tuple]:
        nonlocal last_repair
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
        locate_sessions=locate_sessions,
        auto_read_patterns=config.inbox.auto_read,
        mark_read_after_turn=mark_channel_read_after_turn,
        record_turn=record_channel_turn,
        protected_channels=functools.partial(protected_brief_channels, brief_cache),
        detached_channels=detached_channels,
        tty_processes=tty_processes.by_tty,
    )
