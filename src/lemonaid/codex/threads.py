"""What Codex has stored about threads: lemonaid's one way to ask.

Answers come from the Codex service's snapshot (`service.py`). A thread it hasn't read yet
is asked of a short-lived app-server, and the scout host is started so the service reads it
from then on.
"""

from collections import abc

from ..log import get_logger
from ..watch import scout_start
from . import app_server, snapshot, stored

_log = get_logger("codex.threads")
_TIMEOUT = 5.0

Thread = stored.Thread


def _ask(threads: list[str]) -> dict[str, Thread | None]:
    return app_server.once(
        lambda server: stored.read(server, threads, _TIMEOUT),
        f"{len(threads)} threads",
        {},
        _TIMEOUT,
    )


def get(threads: abc.Iterable[str], running: bool = False) -> dict[str, Thread | None]:
    """Codex's record of each thread it answers for, or None when it has no conversation
    to resume. A thread Codex can't be asked about is left out.

    With *running*, the caller knows the threads are running, so the snapshot's None, which
    may have been read before Codex stored a new thread, is asked again.
    """
    wanted = {thread for thread in threads if thread}
    if not wanted:
        return {}

    snapshot.interested(wanted)
    known = snapshot.read()
    answers = {
        thread: known[thread]
        for thread in wanted
        if thread in known and (known[thread] is not None or not running)
    }
    if (missing := sorted(wanted - answers.keys())) and (asked := _ask(missing)):
        scout_start.ensure_host()  # so the service reads these from now on
        answers |= asked
    return answers


def gone(threads: abc.Iterable[str]) -> set[str]:
    """The *threads* that can't be resumed: blank, unknown to Codex, archived, or whose
    conversation is gone. One Codex can't be asked about is not counted as gone."""
    threads = set(threads)
    answers = get(threads)
    return {
        thread
        for thread in threads
        if not thread
        or (thread in answers and (answers[thread] is None or answers[thread].archived))
    }


def latest_in(cwd: str) -> Thread | None:
    """The most recently updated top-level interactive thread working in *cwd*."""
    return app_server.once(
        lambda server: stored.latest_in(server, cwd, _TIMEOUT), cwd, None, _TIMEOUT
    )


def latest_turns(thread: str, count: int) -> list[stored.Turn]:
    """The thread's newest *count* turns, newest first; none when Codex can't be asked."""
    return app_server.once(
        lambda server: stored.latest_turns(server, thread, count, _TIMEOUT), thread, [], _TIMEOUT
    )
