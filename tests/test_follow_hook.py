"""The follow hook runs inside the tmux server, once per switch, whatever fires it.

A switch fires two hooks. Two background shells each saw the pane absent and
both joined it, and a pane joined twice into one window came out 117 columns
wide instead of 58. Hooks that run in the server run in order, so the second
sees what the first did. The integration tests below drive a real server
because that ordering is the whole point and cannot be faked.
"""

import shutil
import subprocess
import uuid

import pytest

from lemonaid.tmux import follow, scratch


def test_the_hook_never_leaves_the_server():
    command = follow.hook_command()

    assert command.startswith("if-shell -F")
    assert "run-shell -C" in command
    assert "run-shell -b" not in command


def test_the_join_keeps_focus_where_the_switch_put_it():
    """-d instead of a select-pane afterwards, which was a second relayout."""
    assert "join-pane -d" in follow.hook_command()
    assert "select-pane" not in follow.hook_command()


def test_after_select_window_is_retired():
    """It fires alongside session-window-changed on every window switch."""
    assert "after-select-window" not in follow.HOOKS
    assert "after-select-window" in follow.RETIRED_HOOKS


def test_the_parking_session_is_never_a_destination():
    assert "_lma_scratch" in follow.hook_condition()


def test_the_cap_measures_the_client_and_falls_back_to_the_window():
    command = follow.hook_command()

    assert "#{client_width}" in command and "#{window_width}" in command
    assert "#{client_height}" in command and "#{window_height}" in command


# --- against a real server -------------------------------------------------


@pytest.fixture
def tmux(monkeypatch, tmp_path):
    """A throwaway server with two 245x90 sessions, a parking session, and a
    control-mode client attached to `a` so switch-client and client_width work.

    $TMUX is pointed at it, so the plain `tmux` that follow.py and scratch.py
    run reaches this server and no other.
    """
    if not shutil.which("tmux"):
        pytest.skip("tmux not installed")

    name = f"lemonaid-test-{uuid.uuid4().hex[:8]}"

    def run(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["tmux", "-L", name, *args], capture_output=True, text=True)

    started = run("-f", "/dev/null", "new-session", "-d", "-s", "a", "-n", "w1", "-x", "245", "-y", "90")
    if started.returncode != 0:
        pytest.skip(f"cannot start tmux: {started.stderr.strip()}")

    run("new-window", "-d", "-t", "a", "-n", "w2")  # -d: w1 stays current, so w2 is a change
    run("new-session", "-d", "-s", "b", "-n", "w1", "-x", "245", "-y", "90")
    run("new-window", "-d", "-t", "b", "-n", "w2")
    run("new-session", "-d", "-s", scratch._SCRATCH_SESSION, "-x", "245", "-y", "90", "sh")
    client = subprocess.Popen(
        ["tmux", "-L", name, "-C", "attach", "-t", "a"],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    run("refresh-client", "-C", "245x90")
    monkeypatch.setenv("TMUX", f"{run('display', '-p', '#{socket_path}').stdout.strip()},0,0")
    monkeypatch.setattr(scratch, "get_state_path", lambda: tmp_path)
    try:
        yield run
    finally:
        client.kill()
        run("kill-server")


def _panes(run, window: str) -> list[tuple[str, int, int, bool]]:
    """(pane_id, width, height, active) for each pane in `window`."""
    out = run("list-panes", "-t", window, "-F", "#{pane_id} #{pane_width} #{pane_height} #{pane_active}")
    return [
        (p, int(w), int(h), a == "1") for p, w, h, a in (line.split() for line in out.stdout.split("\n") if line)
    ]


def _followed_pane(run, **options: str) -> str:
    """Mark the parking session's pane as the scratch pane, following left at 58."""
    pane = run("display", "-t", scratch._SCRATCH_SESSION, "-p", "#{pane_id}").stdout.strip()
    scratch._mark_pane(pane)
    scratch._save_pane_id(pane)
    follow.publish(
        {
            follow.FOLLOW_OPTION: "on",
            follow.POSITION_OPTION: "left",
            follow.WIDTH_OPTION: "58",
            follow.HEIGHT_OPTION: "12",
            **options,
        }
    )
    follow.install_hooks()
    return pane


def test_the_pane_follows_a_window_switch(tmux):
    pane = _followed_pane(tmux)

    tmux("select-window", "-t", "a:w2")

    assert (pane, 58, 90, False) in _panes(tmux, "a:w2")


def test_a_switch_that_fires_two_hooks_joins_once(tmux):
    """switch-client to a session:window fires session-window-changed and
    client-session-changed. The second must find the pane already there."""
    pane = _followed_pane(tmux)

    tmux("switch-client", "-t", "b:w2")

    panes = _panes(tmux, "b:w2")
    assert len(panes) == 2
    assert (pane, 58, 90, False) in panes


def test_the_switch_target_keeps_focus(tmux):
    _followed_pane(tmux)

    tmux("switch-client", "-t", "b:w1")

    assert tmux("display", "-p", "#{pane_id}").stdout.strip() != scratch._get_pane_id()


def test_a_top_pane_is_measured_in_rows(tmux):
    pane = _followed_pane(tmux, **{follow.POSITION_OPTION: "top"})

    tmux("select-window", "-t", "a:w2")

    assert (pane, 245, 12, False) in _panes(tmux, "a:w2")


def test_a_saved_size_yields_to_the_cap(tmux):
    pane = _followed_pane(tmux, **{follow.WIDTH_OPTION: "200"})

    tmux("select-window", "-t", "a:w2")

    assert (pane, int(245 * follow.MAX_SHARE), 90, False) in _panes(tmux, "a:w2")


def test_follow_off_leaves_the_pane_where_it_is(tmux):
    _followed_pane(tmux, **{follow.FOLLOW_OPTION: "off"})

    tmux("select-window", "-t", "a:w2")

    assert len(_panes(tmux, "a:w2")) == 1


def test_a_parked_pane_stays_parked(tmux):
    """q clears the state; the hook must see that without a file to read."""
    _followed_pane(tmux)
    scratch._clear_state()

    tmux("select-window", "-t", "a:w2")

    assert len(_panes(tmux, "a:w2")) == 1


def test_a_dead_pane_is_no_error(tmux):
    pane = _followed_pane(tmux)
    tmux("kill-pane", "-t", pane)

    assert tmux("select-window", "-t", "a:w2").returncode == 0
    assert len(_panes(tmux, "a:w2")) == 1
