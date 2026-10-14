"""Which path a Claude lemon's watch batches and messages take, judged from what is running now."""

import typing as ty

from ..claude import inbound
from . import push_scout, wait_state


class Path(ty.NamedTuple):
    text: str
    loud: bool  # the message may never be read, or may be held for approval


class Facts(ty.NamedTuple):
    socket: bool
    setting: str  # "accepted", "not accepted" or "unknown"
    scout: bool
    waiter: bool


def gather(lemon_id: str, session_id: str) -> Facts:
    entry = push_scout.session(session_id)
    return Facts(
        entry is not None,
        inbound.session_setting(entry) if entry is not None else "",
        push_scout.running(lemon_id, session_id),
        wait_state.is_armed(lemon_id),
    )


def path_of(found: Facts) -> Path:
    if not found.socket:
        if found.waiter:
            return Path("queued for its background waiter", False)

        return Path("no session socket; it reads this only when it next arms a waiter", True)

    if found.setting != "accepted":
        if found.waiter:
            return Path("queued for its background waiter", False)

        return Path(
            f"session socket found but the session may hold pushed messages for approval "
            f"(crossSessionInbound: {found.setting})",
            True,
        )

    if found.scout:
        return Path("pushed through the session socket", False)

    if found.waiter:
        return Path("queued for its background waiter", False)

    return Path(
        "session socket found but no scout is running; it reads this when it next arms a waiter",
        True,
    )


def status_line(found: Facts) -> str:
    """`watch --self --status`'s account of this session's own path."""
    return (
        f"socket {'found' if found.socket else 'missing'}"
        + (f", crossSessionInbound {found.setting}" if found.socket else "")
        + f", scout {'running' if found.scout else 'not running'}"
        + f", batches: {path_of(found).text}"
    )
