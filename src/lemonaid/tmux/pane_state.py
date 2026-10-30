"""Where each tmux client and pane is, as the scout host's label client last listed them.

The label client lists a server's clients and panes whenever its control connection
reports a change, and keeps the listing in one file per server. While it holds that
file's lock the listing is current, so a reader uses it instead of running `tmux`.
"""

import hashlib
import json
import os
import pathlib
import typing as ty

from ..watch import waiter_lock

SUBSCRIPTION = "lemonaid-panes"
CLIENT_FIELDS = (
    "client_name",
    "window_id",
    "client_width",
    "client_height",
    "@lemonaid_scratch",
    "pane_tty",
)
PANE_FIELDS = (
    "pane_id",
    "window_id",
    "pane_active",
    "pane_last",
    "window_active",
    "session_attached",
    "@lemonaid_scratch",
    "window_index",
    "session_created",
    "start_time",
    "session_id",
    "pane_width",
    "pane_height",
    "pane_tty",
    "session_name",  # the one free text field, last
)
# Changes when a listed field does that tmux sends no notification for; tmux checks
# subscriptions once a second.
CHANGES = (
    "#{S:#{session_id}|#{session_name}|#{session_attached};"
    "#{W:#{window_id}|#{window_index}|#{window_active}|#{window_zoomed_flag}"
    "|#{window_width}|#{window_height};"
    "#{P:#{pane_id}|#{pane_active}|#{pane_last}|#{pane_width}|#{pane_height}"
    "|#{@lemonaid_scratch};}}}#{@lemonaid_scratch_geometry_epoch}"
)
# Notifications after which the listing is taken again at once.
NOTIFICATIONS = (
    "%window-pane-changed ",
    "%session-window-changed ",
    "%client-session-changed ",
    "%client-detached ",
    "%sessions-changed",
    "%session-renamed ",
    "%window-add ",
    "%window-close ",
    "%unlinked-window-close ",
    "%layout-change ",
)

Row = dict[str, str]


class State(ty.NamedTuple):
    clients: list[Row]
    panes: list[Row]


def listing(fields: tuple[str, ...]) -> str:
    return "\t".join(f"#{{{field}}}" for field in fields)


def _rows(fields: tuple[str, ...], lines: list[str]) -> list[Row]:
    return [
        dict(zip(fields, parts, strict=True))
        for line in lines
        if len(parts := line.split("\t", len(fields) - 1)) == len(fields)
    ]


def _stem(socket: str) -> pathlib.Path:
    state = os.environ.get("LEMONAID_STATE_DIR") or "~/.local/state/lemonaid"
    digest = hashlib.sha256(socket.encode()).hexdigest()[:16]
    return pathlib.Path(state).expanduser() / "tmux-panes" / digest


def lock_path(socket: str) -> pathlib.Path:
    return _stem(socket).with_suffix(".lock")


def publish(socket: str, clients: list[str], panes: list[str]) -> None:
    """Keep the listing for *socket*, rewriting the file only when it changed."""
    path = _stem(socket).with_suffix(".json")
    text = json.dumps(
        {"clients": _rows(CLIENT_FIELDS, clients), "panes": _rows(PANE_FIELDS, panes)}
    )
    try:
        if path.read_text() == text:
            return

    except FileNotFoundError:
        path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f".{os.getpid()}.tmp")
    temporary.write_text(text)
    temporary.replace(path)


def read(socket: str | None) -> State | None:
    """The current listing of *socket*'s server (by default this pane's), or None when no
    label client keeps one."""
    socket = socket or os.environ.get("TMUX", "").split(",")[0]
    if not socket or not waiter_lock.held(lock_path(socket)):
        return None

    try:
        found = json.loads(_stem(socket).with_suffix(".json").read_text())
        return State(found["clients"], found["panes"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def version(socket: str | None) -> int | None:
    """Changes whenever the kept listing does; None when no label client keeps one."""
    socket = socket or os.environ.get("TMUX", "").split(",")[0]
    if not socket or not waiter_lock.held(lock_path(socket)):
        return None

    try:
        return _stem(socket).with_suffix(".json").stat().st_mtime_ns
    except OSError:
        return None


def focused_ttys(state: State) -> set[str]:
    """As `navigation.focused_ttys` finds them."""
    scratch_windows = {c["window_id"] for c in state.clients if c["@lemonaid_scratch"] == "1"}
    return {c["pane_tty"] for c in state.clients if c["pane_tty"]} | {
        p["pane_tty"]
        for p in state.panes
        if p["window_id"] in scratch_windows
        and p["pane_last"] == "1"
        and p["@lemonaid_scratch"] != "1"
        and p["pane_tty"]
    }


def receives_keys(state: State, pane: str) -> bool | None:
    """Whether *pane* is selected in a visible, attached window; None when it isn't listed."""
    rows = [p for p in state.panes if p["pane_id"] == pane]
    if not rows:
        return None

    return any(
        p["pane_active"] == "1"
        and p["window_active"] == "1"
        and p["session_attached"].isdecimal()
        and int(p["session_attached"]) > 0
        for p in rows
    )
