"""Which Codex processes run which threads, from what hooks recorded and `ps`."""

import os
import subprocess

import pytest

from lemonaid.codex import processes
from lemonaid.launch.restart import state

_thread_ttys = processes.thread_ttys
_open_threads = processes.open_threads

_AUTHOR = "01a1f6f1-0000-7000-8000-000000000000"
_REVIEWER = "01a1f6f1-0000-7000-8000-000000000001"
_RESUMED = "01a182a4-4cc5-7a20-991d-97b6f61e0743"
_STARTED = "Mon Nov 16 18:27:18 2026"
_CODEX = "/opt/codex/bin/codex"


def _record(pid: int, thread: str, tty: str, started: str = _STARTED, at: float = 0.0) -> None:
    """A hook in *thread* recorded the Codex process *pid*."""
    name = f"native-{state.key(f'codex:{thread}')}.json"
    state.write(
        name,
        {
            "session_id": thread,
            "identity": {
                "pid": pid,
                "parent": 1,
                "tty": tty,
                "started": started,
                "executable": _CODEX,
            },
        },
    )
    if at:
        os.utime(state.root() / name, (at, at))


def _ps(monkeypatch, *rows: str, returncode: int = 0) -> None:
    """`ps -A` lists *rows*, each `pid stat tty lstart args`."""
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda argv, **kwargs: subprocess.CompletedProcess(
            argv, returncode, stdout="".join(f"{row}\n" for row in rows), stderr=""
        ),
    )


def test_each_recorded_live_process_names_its_thread_and_terminal(monkeypatch):
    _record(11, _AUTHOR, "ttys001")
    _record(22, _REVIEWER, "ttys002")
    _ps(
        monkeypatch,
        f"11 S+ ttys001 {_STARTED} {_CODEX} --no-daemon",
        f"22 S+ ttys002 {_STARTED} {_CODEX}",
        f"33 S ttys003 {_STARTED} /bin/zsh",
    )

    assert _thread_ttys() == {_AUTHOR: {"/dev/ttys001"}, _REVIEWER: {"/dev/ttys002"}}
    assert processes.executable(_AUTHOR) == _CODEX


def test_a_process_that_has_restarted_or_exited_runs_nothing(monkeypatch):
    _record(11, _AUTHOR, "ttys001")
    _record(22, _REVIEWER, "ttys002")
    _ps(monkeypatch, f"11 S+ ttys001 Tue Nov 17 09:00:00 2026 {_CODEX}")

    assert _open_threads() == set()


def test_the_thread_a_process_reported_last_is_the_one_it_runs(monkeypatch):
    _record(11, _AUTHOR, "ttys001", at=1_795_000_000)
    _record(11, _REVIEWER, "ttys001", at=1_795_000_100)  # after /clear
    _ps(monkeypatch, f"11 S+ ttys001 {_STARTED} {_CODEX}")

    assert _thread_ttys() == {_REVIEWER: {"/dev/ttys001"}}


def test_a_resumed_process_no_hook_has_reported_runs_the_thread_it_resumed(monkeypatch):
    _ps(monkeypatch, f"17369 S+ ttys016 {_STARTED} {_CODEX} -c x=1 resume {_RESUMED}")

    assert _thread_ttys() == {_RESUMED: {"/dev/ttys016"}}
    assert processes.executable(_RESUMED) == _CODEX


def test_the_shared_daemon_runs_its_threads_in_no_terminal(monkeypatch):
    _record(11, _AUTHOR, "??")
    _ps(
        monkeypatch,
        f"11 Ss ?? {_STARTED} {_CODEX} app-server --listen unix:// --managed-daemon",
        f"12 S ?? {_STARTED} {_CODEX}",
    )

    assert _thread_ttys() == {}
    assert _open_threads() == {_AUTHOR}


@pytest.mark.parametrize("failure", [OSError("denied"), subprocess.TimeoutExpired("ps", 1)])
def test_a_failed_listing_is_unknown(monkeypatch, failure):
    def run(*args, **kwargs):
        raise failure

    monkeypatch.setattr(subprocess, "run", run)

    assert _thread_ttys() is None
    assert _open_threads() is None


def test_the_shared_daemon_runs_every_thread_it_reported(monkeypatch):
    _record(11, _AUTHOR, "??", at=1_795_000_000)
    _record(11, _REVIEWER, "??", at=1_795_000_100)
    _ps(monkeypatch, f"11 Ss ?? {_STARTED} {_CODEX} app-server --listen unix://")

    assert _open_threads() == {_AUTHOR, _REVIEWER}
    assert _thread_ttys() == {}
