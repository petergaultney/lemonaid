import os
import subprocess
import sys

from lemonaid.front_end import location
from lemonaid.lsp import registry


def _in_session(session: str) -> location.Location:
    return location.Location("tmux", "/tmp/tmux-1/default", session)


def _record(pid: int, *, session: str = "", started: float = 0.0) -> registry.Record:
    return registry.Record(
        pid=pid,
        socket=f"/s/{pid}.sock",
        roots=("/work",),
        location=_in_session(session),
        started=started,
    )


def test_servers_in_the_caller_s_session_come_first_then_the_newest() -> None:
    old_here = _record(1, session="tools", started=1)
    new_elsewhere = _record(2, session="notes", started=2)
    newest_here = _record(3, session="tools", started=3)

    ordered = registry.by_preference([old_here, new_elsewhere, newest_here], _in_session("tools"))

    assert [r.pid for r in ordered] == [3, 1, 2]


def test_a_record_whose_process_is_gone_is_removed() -> None:
    finished = subprocess.run(
        [sys.executable, "-c", "import os; print(os.getpid())"], capture_output=True, text=True
    )
    gone = _record(int(finished.stdout))
    registry.write(gone)
    registry.write(_record(os.getpid(), session="tools"))

    assert registry.live() == [_record(os.getpid(), session="tools")]
    assert not (registry.directory() / f"{gone.pid}.json").exists()


def test_a_record_covers_paths_under_its_roots() -> None:
    record = _record(1)

    assert record.covers(registry.Path("/work/a/b.py"))
    assert not record.covers(registry.Path("/workshop/b.py"))


def test_a_state_directory_too_long_for_a_socket_gives_none(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("LEMONAID_STATE_DIR", str(tmp_path / ("x" * 120)))

    assert registry.socket_path(1) is None
