"""Which Claude session a tty runs: only a live `claude` process that wrote the file counts."""

import calendar
import json
import os
import time

import pytest

from lemonaid.claude import live_sessions, session_socket

_FORMAT = "%a %b %d %H:%M:%S %Y"
_STARTED_UTC = "Sat Oct 24 13:31:18 2026"  # what Claude Code writes


def _listed(pid: int) -> None:
    sessions = session_socket.claude_dir() / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    (sessions / f"{pid}.json").write_text(
        json.dumps(
            {
                "pid": pid,
                "sessionId": "real-hq",
                "messagingSocketPath": "/tmp/x.sock",
                "procStart": _STARTED_UTC,
            }
        )
    )


@pytest.mark.parametrize(
    ("command", "started", "expected"),
    [
        pytest.param("claude --resume real-hq", None, {"/dev/ttys001": {"real-hq"}}, id="claude"),
        pytest.param("python -m pytest", None, {}, id="pid-reused-by-another-program"),
        pytest.param("claude", "Sat Oct 24 01:00:00 2026", {}, id="pid-reused-by-another-claude"),
    ],
)
def test_a_session_file_counts_only_for_the_process_that_wrote_it(
    monkeypatch, command, started, expected
):
    pid = os.getpid()
    _listed(pid)
    lstart = started or time.strftime(
        _FORMAT, time.localtime(calendar.timegm(time.strptime(_STARTED_UTC, _FORMAT)))
    )
    monkeypatch.setattr(
        live_sessions, "_listing", lambda pids: f"{pid} ttys001 {lstart} {command}\n"
    )

    assert live_sessions.by_tty() == expected
