import os
import subprocess
import sys

import pytest

from lemonaid.lsp import registry


def _record(pid: int, *, tmux: str | None = None, started: float = 0.0) -> registry.Record:
    return registry.Record(
        pid=pid, socket=f"/s/{pid}.sock", roots=("/work",), tmux=tmux, started=started
    )


@pytest.mark.parametrize(
    ("tmux", "session"),
    [("/tmp/tmux-1/default,123,4", "/tmp/tmux-1/default,4"), ("", None), ("x,1", None)],
)
def test_the_tmux_session_comes_from_the_socket_and_session_id(tmux, session) -> None:
    assert registry.tmux_session({"TMUX": tmux}) == session


def test_servers_in_the_caller_s_session_come_first_then_the_newest() -> None:
    old_here = _record(1, tmux="s,1", started=1)
    new_elsewhere = _record(2, tmux="s,2", started=2)
    newest_here = _record(3, tmux="s,1", started=3)

    ordered = registry.by_preference([old_here, new_elsewhere, newest_here], "s,1")

    assert [r.pid for r in ordered] == [3, 1, 2]


def test_a_record_whose_process_is_gone_is_removed() -> None:
    finished = subprocess.run(
        [sys.executable, "-c", "import os; print(os.getpid())"], capture_output=True, text=True
    )
    gone = _record(int(finished.stdout))
    registry.write(gone)
    registry.write(_record(os.getpid()))

    assert [r.pid for r in registry.live()] == [os.getpid()]
    assert not (registry.directory() / f"{gone.pid}.json").exists()


def test_a_record_covers_paths_under_its_roots() -> None:
    record = _record(1)

    assert record.covers(registry.Path("/work/a/b.py"))
    assert not record.covers(registry.Path("/workshop/b.py"))


def test_a_state_directory_too_long_for_a_socket_gives_none(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("LEMONAID_STATE_DIR", str(tmp_path / ("x" * 120)))

    assert registry.socket_path(1) is None
