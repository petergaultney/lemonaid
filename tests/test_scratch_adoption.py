"""Finding an existing scratch pane instead of creating a second one.

The state file is the fast path. When it is lost or stale, the @lemonaid_scratch
marker is what still identifies the pane - including after it has been joined
into one of the user's windows, which leaves the scratch session empty and
defeats the session-based recovery.
"""

import subprocess

from lemonaid.tmux import scratch


def _panes(monkeypatch, listing: str, killed: list[str] | None = None) -> None:
    """Stand in for tmux list-panes -a, recording any kill-pane calls."""

    def _run(argv, **kwargs):
        if "list-panes" in argv:
            return subprocess.CompletedProcess(argv, 0, stdout=listing, stderr="")
        if "kill-pane" in argv and killed is not None:
            killed.append(argv[argv.index("-t") + 1])
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", _run)


def test_only_marked_panes_are_found(monkeypatch):
    """An unmarked pane is somebody else's, whatever its id looks like."""
    _panes(monkeypatch, "%1 1\n%2 \n%3 1\n")

    assert scratch._find_marked_panes() == ["%1", "%3"]


def test_no_marked_panes_means_nothing_to_adopt(monkeypatch, tmp_path):
    monkeypatch.setattr(scratch, "get_state_path", lambda: tmp_path)
    _panes(monkeypatch, "%1 \n%2 \n")

    assert scratch._adopt_existing_pane() is None


def test_a_lone_pane_is_adopted_and_recorded(monkeypatch, tmp_path):
    monkeypatch.setattr(scratch, "get_state_path", lambda: tmp_path)
    _panes(monkeypatch, "%7 1\n")

    assert scratch._adopt_existing_pane() == "%7"
    assert scratch._state_path().read_text() == "%7"


def test_extra_panes_are_killed_so_one_view_survives(monkeypatch, tmp_path):
    """Two TUIs poll independently and disagree about what is unread."""
    monkeypatch.setattr(scratch, "get_state_path", lambda: tmp_path)
    killed: list[str] = []
    _panes(monkeypatch, "%1 1\n%2 1\n%9 1\n", killed)

    assert scratch._adopt_existing_pane() == "%9"
    assert killed == ["%1", "%2"]


def test_a_failed_listing_adopts_nothing(monkeypatch, tmp_path):
    """Same rule as the archiver: not being able to ask is not an answer."""
    monkeypatch.setattr(scratch, "get_state_path", lambda: tmp_path)

    def _run(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 1, stdout="", stderr="no server")

    monkeypatch.setattr(subprocess, "run", _run)

    assert scratch._find_marked_panes() == []
    assert scratch._adopt_existing_pane() is None


def test_each_tmux_server_tracks_its_own_pane(monkeypatch, tmp_path):
    """A second terminal running its own tmux server gets its own scratch pane."""
    monkeypatch.setattr(scratch, "get_state_path", lambda: tmp_path)

    monkeypatch.setenv("TMUX", "/tmp/tmux-501/default,123,0")
    default_path = scratch._state_path()
    monkeypatch.setenv("TMUX", "/tmp/tmux-501/work,456,0")
    work_path = scratch._state_path()

    assert default_path != work_path
