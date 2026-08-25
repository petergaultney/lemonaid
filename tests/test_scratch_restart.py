"""Restarting the TUI without disturbing the pane it runs in.

What these pin is that the pane survives: `respawn-pane -k` rather than a kill
and a recreate, and the marker put back afterwards. In follow mode the pane sits
in one of the user's windows with placeholders held in every window it has
visited, and all of that is addressed by pane id.
"""

import subprocess

from lemonaid.tmux import restart, scratch


def _tmux(monkeypatch, calls: list[list[str]], respawn_rc: int = 0) -> None:
    """Record every tmux call, and let respawn-pane report `respawn_rc`."""

    def _run(argv, **kwargs):
        calls.append(argv)
        rc = respawn_rc if "respawn-pane" in argv else 0
        return subprocess.CompletedProcess(argv, rc, stdout="", stderr="no such pane")

    monkeypatch.setattr(subprocess, "run", _run)


def test_the_pane_is_respawned_rather_than_killed(monkeypatch):
    """A kill would discard the follow-mode arrangement built around this pane."""
    calls: list[list[str]] = []
    _tmux(monkeypatch, calls)
    monkeypatch.setattr(scratch, "marked_pane", lambda: "%7")

    assert restart.restart_scratch() == "restarted %7"

    respawned = [c for c in calls if "respawn-pane" in c]
    assert len(respawned) == 1
    assert respawned[0] == ["tmux", "respawn-pane", "-k", "-t", "%7", "lma --scratch"]
    assert not [c for c in calls if "kill-pane" in c]


def test_the_marker_is_reasserted(monkeypatch):
    """Whether a respawn keeps pane options is a tmux detail; the marker is how
    every other command finds this pane, so restart does not rely on it."""
    calls: list[list[str]] = []
    _tmux(monkeypatch, calls)
    monkeypatch.setattr(scratch, "marked_pane", lambda: "%7")

    restart.restart_scratch()

    assert ["tmux", "set-option", "-p", "-t", "%7", "@lemonaid_scratch", "1"] in calls


def test_no_pane_is_not_an_error(monkeypatch):
    """Nothing is running, which is what `prefix+l` is for - not a failure."""
    calls: list[list[str]] = []
    _tmux(monkeypatch, calls)
    monkeypatch.setattr(scratch, "marked_pane", lambda: None)

    assert restart.restart_scratch() == "no scratch pane to restart; create one first"
    assert not [c for c in calls if "respawn-pane" in c]


def test_a_failed_respawn_leaves_the_marker_alone(monkeypatch):
    """The pane it names is gone or not ours; marking it would claim a stranger."""
    calls: list[list[str]] = []
    _tmux(monkeypatch, calls, respawn_rc=1)
    monkeypatch.setattr(scratch, "marked_pane", lambda: "%7")

    assert restart.restart_scratch() == "could not restart %7"
    assert not [c for c in calls if "set-option" in c]


def test_a_stale_state_file_falls_back_to_the_marker(monkeypatch, tmp_path):
    """The file names a pane that no longer exists; the marker still finds the real one."""
    monkeypatch.setattr(scratch, "get_state_path", lambda: tmp_path)

    def _run(argv, **kwargs):
        if "display-message" in argv:  # _pane_exists on the stale id
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
        if "list-panes" in argv:
            return subprocess.CompletedProcess(argv, 0, stdout="%9 1\n", stderr="")
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", _run)
    scratch._save_pane_id("%3")

    assert scratch.marked_pane() == "%9"
