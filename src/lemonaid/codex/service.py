"""The Codex service: one warm app-server in the scout host, keeping the snapshot current.

It re-reads every thread someone has asked about each `INTERVAL`, and sooner when someone
asks about a thread it hasn't read. It starts a new server when the old one dies or stops answering, and when
the `codex` executable changes, so an upgraded Codex answers. It keeps the host up for
`KEEP_UP` after the last question, since with none asked there is nothing to keep current.
"""

import dataclasses
import os
import shutil
import threading
import time

from ..log import get_logger
from ..watch import host_services
from . import app_server, snapshot, stored, thread_name

_log = get_logger("codex.service")

INTERVAL = 60.0
KEEP_UP = 600.0
_LOOK = 5.0  # seconds between looks for new questions
_TIMEOUT = 30.0


@dataclasses.dataclass
class _State:
    server: app_server.Server | None = None
    executable: tuple[str, int] = ("", 0)  # path and mtime of the `codex` it started
    refreshed: float = 0.0  # Unix seconds of the last refresh
    worker: threading.Thread | None = None
    tried: set[str] = dataclasses.field(default_factory=set)  # threads the last refresh asked
    looked: float = 0.0  # Unix seconds of the last look for new questions
    recent: int = 0  # threads asked about within KEEP_UP, as of that look
    unavailable: bool = False  # the last refresh could not start or ask Codex


def _executable() -> tuple[str, int]:
    path = shutil.which("codex") or ""
    try:
        return path, os.stat(path).st_mtime_ns if path else 0
    except OSError:
        return path, 0


def _server(state: _State) -> app_server.Server | None:
    executable = _executable()
    if state.server is not None and (not state.server.alive() or executable != state.executable):
        state.server.close()
        state.server = None
    if state.server is None:
        state.server, state.executable = app_server.start(_TIMEOUT), executable
    return state.server


def _refresh(state: _State, threads: set[str]) -> None:
    started = time.time()
    state.tried = threads  # tried, answered or not, so an unavailable Codex isn't new work
    if (server := _server(state)) is None:
        state.unavailable = True
        return

    try:
        answers = stored.read(server, threads, _TIMEOUT)
    except (app_server.NoAnswer, OSError, ValueError, KeyError, TypeError) as error:
        _log.warning("codex app-server did not answer for %d threads: %s", len(threads), error)
        server.close()
        state.server, state.unavailable = None, True
        return

    snapshot.write(answers)
    state.refreshed, state.unavailable = started, False
    try:
        thread_name.catch_up(server, answers)
    except (app_server.NoAnswer, OSError, ValueError, KeyError, TypeError) as error:
        _log.warning("codex app-server did not take a thread name: %s", error)


def tick(state: _State, quitting: threading.Event) -> int:
    """Start a refresh when one is due; how many threads were asked about lately."""
    now = time.time()
    if quitting.is_set() or now - state.looked < _LOOK:
        return state.recent

    state.looked = now
    asked = snapshot.interest()
    # With no Codex to ask, the service doesn't keep the host up by itself.
    state.recent = (
        0 if state.unavailable else sum(1 for when in asked.values() if now - when < KEEP_UP)
    )
    due = now - state.refreshed >= INTERVAL or not asked.keys() <= state.tried
    if due and asked and not (state.worker is not None and state.worker.is_alive()):
        state.worker = threading.Thread(
            target=_refresh, args=(state, set(asked)), name="codex-service", daemon=True
        )
        state.worker.start()
    return state.recent


def service() -> host_services.Service:
    state = _State()

    def join() -> None:
        if state.worker is not None:
            state.worker.join(timeout=_TIMEOUT)
        if state.server is not None:
            state.server.close()

    return host_services.Service(
        lambda quitting: tick(state, quitting),
        join,
        lambda: not snapshot.interest().keys() <= state.tried,
    )
