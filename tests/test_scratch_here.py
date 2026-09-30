"""The toggle acts on the session whose key ran it.

A `run-shell` binding has no TMUX_PANE, and a bare `tmux display-message -p`
names the session with the newest activity. A session another process created
in the moment after the keypress was newer, so the toggle read its window as
here and joined the scratch pane into it, out of the window you were in.
"""

import shutil
import subprocess
import uuid

import pytest

from lemonaid.tmux import here, scratch


def test_a_pane_names_itself(monkeypatch):
    monkeypatch.setenv("TMUX_PANE", "%12")

    assert here.target() == ["-t", "%12"]


def test_a_run_shell_job_names_its_session(monkeypatch):
    monkeypatch.delenv("TMUX_PANE", raising=False)
    monkeypatch.setenv("TMUX", "/tmp/tmux-501/default,4242,7")

    assert here.target() == ["-t", "$7"]


def test_outside_tmux_there_is_nothing_to_name(monkeypatch):
    monkeypatch.delenv("TMUX_PANE", raising=False)
    monkeypatch.delenv("TMUX", raising=False)

    assert here.target() == []


@pytest.fixture
def tmux(monkeypatch, tmp_path):
    """A server whose session `a` holds a followed scratch pane beside a shell,
    seen from a run-shell job in `a`: TMUX names `a`, and there is no TMUX_PANE.

    Session `b` is created afterwards, so it has the newer activity.
    """
    if not shutil.which("tmux"):
        pytest.skip("tmux not installed")

    name = f"lemonaid-test-{uuid.uuid4().hex[:8]}"

    def run(*args: str) -> str:
        return subprocess.run(
            ["tmux", "-L", name, *args], capture_output=True, text=True
        ).stdout.strip()

    started = subprocess.run(
        ["tmux", "-L", name, "-f", "/dev/null", "new-session", "-d", "-s", "a", "-x", "200"],
        capture_output=True,
        text=True,
    )
    if started.returncode != 0:
        pytest.skip(f"cannot start tmux: {started.stderr.strip()}")

    pane = run("split-window", "-d", "-h", "-b", "-t", "a", "-P", "-F", "#{pane_id}", "sleep 60")
    session = run("display", "-t", "a", "-p", "#{session_id}")
    monkeypatch.setenv("TMUX", f"{run('display', '-p', '#{socket_path}')},0,{session[1:]}")
    monkeypatch.delenv("TMUX_PANE", raising=False)
    monkeypatch.setattr(scratch, "get_state_path", lambda: tmp_path)
    scratch._mark_pane(pane)
    scratch._save_pane_id(pane)
    scratch.set_follow_enabled(True)
    run("new-session", "-d", "-s", "b")
    try:
        yield run, pane
    finally:
        run("kill-server")


def test_a_newer_session_does_not_take_the_pane(tmux):
    run, pane = tmux

    assert scratch.toggle_scratch(size="40", position="left") == "selected"
    assert run("display", "-t", pane, "-p", "#{session_name}") == "a"
    assert run("display", "-t", "a", "-p", "#{pane_id}") == pane


def test_defocusing_stays_in_the_session_that_asked(tmux):
    run, pane = tmux
    run("select-pane", "-t", pane)
    run("new-session", "-d", "-s", "c")  # newer again, after the select

    assert scratch.toggle_scratch(size="40", position="left") == "defocused"
    assert run("display", "-t", "a", "-p", "#{pane_id}") != pane
    assert run("display", "-t", pane, "-p", "#{session_name}") == "a"


def test_a_malformed_tmux_names_nothing(monkeypatch):
    monkeypatch.delenv("TMUX_PANE", raising=False)
    monkeypatch.setenv("TMUX", "/tmp/tmux-501/default")

    assert here.target() == []


def test_with_nothing_to_name_tmux_is_not_asked(monkeypatch):
    """An untargeted query would answer with the newest session."""
    monkeypatch.delenv("TMUX_PANE", raising=False)
    monkeypatch.delenv("TMUX", raising=False)

    def _run(argv, **kwargs):
        raise AssertionError(f"ran {argv}")

    monkeypatch.setattr(subprocess, "run", _run)

    assert scratch._get_current_window() is None
    assert scratch._get_current_pane() is None


def test_a_session_that_has_ended_moves_nothing(tmux, monkeypatch):
    run, pane = tmux
    socket = run("display", "-p", "#{socket_path}")
    monkeypatch.setenv("TMUX", f"{socket},0,99")

    assert scratch.toggle_scratch(size="40", position="left") == "no target"
    assert run("display", "-t", pane, "-p", "#{session_name}") == "a"


def test_an_unnamed_session_moves_nothing(tmux, monkeypatch):
    run, pane = tmux
    monkeypatch.setenv("TMUX", run("display", "-p", "#{socket_path}"))

    assert scratch.ensure_scratch(size="40", position="left") == "no target"
    assert run("display", "-t", pane, "-p", "#{session_name}") == "a"
