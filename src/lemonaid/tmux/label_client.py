"""Keep one tmux server's tab labels current through a control-mode client.

The client attaches to its own session, `_lma_labels`, so no lemon's session counts it as
a viewer, and ignores size, so it never resizes a window. Format subscriptions covering
every window of every session tell it when any window's label inputs, or any client or
pane's place, change; `label_session` then lists them again.
"""

import contextlib
import subprocess
import tempfile
import threading
import typing as ty

from ..log import get_logger
from . import label_session, pane_state, window_labels

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


def _subscribe(session: label_session.Session) -> None:
    session.send("refresh-client -f no-output,ignore-size")
    session.send(
        "refresh-client -B "
        + window_labels.quoted(f"{window_labels.SUBSCRIPTION}::{window_labels.CHANGES}")
    )
    session.ask("windows")
    if session.socket:
        session.send(
            "refresh-client -B "
            + window_labels.quoted(f"{pane_state.SUBSCRIPTION}::{pane_state.CHANGES}")
        )
        session.ask("panes")


def _serve(session: label_session.Session) -> None:
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
            if kind:
                session.listed(kind, block if line.startswith("%end ") else [])
            block = None
        elif line.startswith("%begin "):
            kind = session.awaiting.popleft() if attached and session.awaiting else ""
            block = []
        elif line.startswith("%session-changed ") and not attached:
            attached = True
            _subscribe(session)
        elif line.startswith(f"%subscription-changed {window_labels.SUBSCRIPTION} "):
            session.ask("windows")
        elif (
            attached
            and session.socket
            and line.startswith(
                (f"%subscription-changed {pane_state.SUBSCRIPTION} ", *pane_state.NOTIFICATIONS)
            )
        ):
            session.ask("panes")
        elif line.startswith("%exit"):
            return


def _label(socket: str, stop: threading.Event, errors: ty.IO[str]) -> int:
    """Label until the client exits; its exit code."""
    process = _attach(socket, errors)
    session = label_session.Session(process, socket)

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
        session.close()
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
