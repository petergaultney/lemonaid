"""One label client's control connection: commands in, each answered in order.

It lists two things, each again whenever tmux reports it may have changed, with at most
one listing of each in flight: every window's label inputs, to relabel those that changed,
and every client and pane, to keep as `pane_state` for readers that would otherwise run
`tmux` themselves.
"""

import collections
import subprocess
import threading
import typing as ty

from ..config import load_config
from ..log import get_logger
from ..watch import waiter_lock
from . import pane_state, window_labels

_log = get_logger("tmux.label_session")

Listing = ty.Literal["windows", "panes"]


class Session:
    def __init__(self, process: subprocess.Popen[str], socket: str = "") -> None:
        self.process = process
        self.socket = socket  # "" keeps no pane state
        self.awaiting: collections.deque[str] = collections.deque()  # each sent command's kind
        self.sending = threading.Lock()  # the stopping thread sends too
        self.labelled: dict[str, window_labels.Window] = {}
        self.listing: set[Listing] = set()
        self.changed_while_listing: set[Listing] = set()
        self.clients: list[str] = []
        self.keeping: ty.IO[str] | None = None  # the pane state's lock, once it is current
        self.tried_keeping = False

    def send(self, command: str, kind: str = "") -> None:
        """Send one command, which tmux answers with one response block."""
        assert self.process.stdin is not None
        with self.sending:
            self.awaiting.append(kind)
            self.process.stdin.write(command + "\n")
            self.process.stdin.flush()

    def ask(self, listing: Listing) -> None:
        if listing in self.listing:
            self.changed_while_listing.add(listing)
            return

        self.listing.add(listing)
        if listing == "windows":
            self.send(f"list-windows -a -F {window_labels.quoted(window_labels.FIELDS)}", "windows")
        else:
            fields = window_labels.quoted(pane_state.listing(pane_state.CLIENT_FIELDS))
            self.send(f"list-clients -F {fields}", "clients")
            fields = window_labels.quoted(pane_state.listing(pane_state.PANE_FIELDS))
            self.send(f"list-panes -a -F {fields}", "panes")

    def relabel(self, lines: list[str]) -> None:
        windows = {w.window_id: w for w in map(window_labels.parse, lines) if w}
        named = load_config().tmux_window.named_processes
        commands = [
            command
            for window_id, window in windows.items()
            if self.labelled.get(window_id) != window
            for command in window_labels.set_commands(
                window_id, *window_labels.labels(window, named)
            )
        ]
        self.labelled = windows
        for command in commands:
            self.send(command)

    def keep(self, panes: list[str]) -> None:
        pane_state.publish(self.socket, self.clients, panes)
        if not self.tried_keeping:
            self.tried_keeping = True
            self.keeping = waiter_lock.acquire(pane_state.lock_path(self.socket))
            if self.keeping is None:
                _log.warning("another process keeps the pane state of %s", self.socket)

    def listed(self, kind: str, lines: list[str]) -> None:
        """Handle the answer to one listing command; *lines* is empty when tmux refused it."""
        if kind == "clients":
            self.clients = lines
            return

        if kind == "windows":
            self.relabel(lines)
        elif self.socket:
            self.keep(lines)
        listing: Listing = "windows" if kind == "windows" else "panes"
        self.listing.discard(listing)
        if listing in self.changed_while_listing:
            self.changed_while_listing.discard(listing)
            self.ask(listing)

    def close(self) -> None:
        if self.keeping is not None:
            self.keeping.close()
            self.keeping = None
