"""Keep one tmux server's tab labels current through a control-mode client.

The client attaches to its own session, `_lma_labels`, so no lemon's session counts it as
a viewer, and ignores size, so it never resizes a window. One format subscription covering
every window of every session tells it when any window's label inputs change; it then lists
the windows and relabels only those whose inputs changed.
"""

import collections
import contextlib
import subprocess
import tempfile
import threading
import typing as ty

from ..config import load_config
from ..log import get_logger
from . import window_labels

_log = get_logger("tmux.label_client")

SESSION = "_lma_labels"
_NOTICE = "lemonaid keeps tab labels from this session; it closes when the scout host stops."

Outcome = ty.Literal["gone", "retry", "stopped"]  # gone: its server no longer exists


def _attach(socket: str, errors: ty.IO[str]) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [
            *("tmux", "-N", "-S", socket, "-C"),  # -N: never start a server for a stale socket
            *("new-session", "-A", "-s", SESSION, "-x", "10", "-y", "10"),
            *("/bin/sh", "-c", f"echo '{_NOTICE}'; exec sleep 2147483647"),  # its only pane
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=errors,
        text=True,
        errors="replace",
        start_new_session=True,
    )


def _answers(socket: str) -> bool:
    """Whether a tmux server listens on *socket*; `kill-server` leaves the file behind."""
    try:
        return (
            subprocess.run(
                ["tmux", "-S", socket, "list-sessions"], capture_output=True, timeout=5
            ).returncode
            == 0
        )
    except (OSError, subprocess.TimeoutExpired):
        return False


class _Session:
    """One control connection: commands in, their responses and notifications out, in order."""

    def __init__(self, process: subprocess.Popen[str]) -> None:
        self.process = process
        self.awaiting: collections.deque[str] = collections.deque()  # each sent command's kind
        self.sending = threading.Lock()  # the stopping thread sends too
        self.labelled: dict[str, window_labels.Window] = {}
        self.listing = False
        self.changed_while_listing = False

    def send(self, command: str, kind: str = "") -> None:
        """Send one command, which tmux answers with one response block."""
        assert self.process.stdin is not None
        with self.sending:
            self.awaiting.append(kind)
            self.process.stdin.write(command + "\n")
            self.process.stdin.flush()

    def list_windows(self) -> None:
        if self.listing:
            self.changed_while_listing = True
            return

        self.listing = True
        self.send(f"list-windows -a -F {window_labels.quoted(window_labels.FIELDS)}", "list")

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

    def listed(self, lines: list[str]) -> None:
        self.listing = False
        self.relabel(lines)
        if self.changed_while_listing:
            self.changed_while_listing = False
            self.list_windows()


def _subscribe(session: _Session) -> None:
    session.send("refresh-client -f no-output,ignore-size")
    session.send(
        "refresh-client -B "
        + window_labels.quoted(f"{window_labels.SUBSCRIPTION}::{window_labels.CHANGES}")
    )
    session.list_windows()


def _serve(session: _Session) -> None:
    """Answer tmux until the client exits.

    Nothing is sent until the attach that started the client has finished, which tmux
    reports with `%session-changed`. Every response block after that answers one of ours,
    in order, however a tmux version flags the attach's own block.
    """
    assert session.process.stdout is not None
    block: list[str] | None = None
    kind = ""
    attached = False
    for raw in session.process.stdout:
        line = raw.rstrip("\n")
        if block is not None:
            if not line.startswith(("%end ", "%error ")):
                block.append(line)
                continue

            if line.startswith("%error "):
                _log.warning("tmux refused a label command: %s", " ".join(block))
            if kind == "list":
                session.listed(block if line.startswith("%end ") else [])
            block = None
        elif line.startswith("%begin "):
            kind = session.awaiting.popleft() if attached and session.awaiting else ""
            block = []
        elif line.startswith("%session-changed ") and not attached:
            attached = True
            _subscribe(session)
        elif line.startswith(f"%subscription-changed {window_labels.SUBSCRIPTION} "):
            session.list_windows()
        elif line.startswith("%exit"):
            return


def _label(socket: str, stop: threading.Event, errors: ty.IO[str]) -> int:
    """Label until the client exits; its exit code."""
    process = _attach(socket, errors)
    session = _Session(process)

    def closer() -> None:
        while not stop.wait(1):
            if process.poll() is not None:
                return

        try:
            session.send(f"kill-session -t ={SESSION}")  # which also ends this client
            process.wait(timeout=2)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            process.terminate()

    threading.Thread(target=closer, name="tmux-labels-stop", daemon=True).start()
    try:
        _serve(session)
    except (OSError, ValueError) as error:  # its pipe closed under it
        _log.info("tmux label client for %s ended: %s", socket, error)
    finally:
        if process.poll() is None:
            process.terminate()
        with contextlib.suppress(OSError):  # its server may have closed the pipe first
            if process.stdin:
                process.stdin.close()
        process.wait()
    return process.returncode


def run(socket: str, stop: threading.Event) -> Outcome:
    """Label *socket*'s windows until its server exits (gone) or *stop* is set (stopped)."""
    with tempfile.TemporaryFile("w+") as errors:
        code = _label(socket, stop, errors)
        errors.seek(0)
        if (said := errors.read().strip()) and not stop.is_set():
            _log.warning("tmux label client for %s exited %s: %s", socket, code, said)
    if stop.is_set():
        return "stopped"

    return "retry" if _answers(socket) else "gone"
