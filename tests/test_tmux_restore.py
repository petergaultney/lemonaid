"""Opening a restored lemon's window in tmux."""

import subprocess

from lemonaid.restore import run
from lemonaid.tmux import placement, restore


def _spot(session: str = "relay", index: int = 2, creates: bool = True) -> run.Spot:
    return run.Spot(f"{session}:{index}", "", placement.Spot(session, index, creates, index))


def _recording(monkeypatch, fails: str = "", sessions: tuple[str, ...] = ()) -> list[list[str]]:
    """Record the tmux commands run, failing any that names *fails*; *sessions* exist."""
    argv: list[list[str]] = []
    monkeypatch.setattr(restore, "_client_size", lambda: ("214", "67"))
    monkeypatch.setattr(restore, "_exists", lambda session: session in sessions)

    def output(*a: str) -> tuple[str, str]:
        argv.append(list(a))
        return ("", "no") if fails in a else ("@7", "")

    monkeypatch.setattr(restore, "_output", output)
    monkeypatch.setattr(restore, "_run", lambda *a: output(*a)[1])
    return argv


def test_a_restored_session_is_built_at_the_client_size(monkeypatch):
    """A detached session with no size is 80x24 and stays there until a client
    shows it. The scratch pane then splits its saved width off an 80-column
    window, leaving the main pane below the minimum - and what you see in the
    slot is the placeholder, a bare `sleep`, which renders as an empty pane."""
    argv = _recording(monkeypatch)
    monkeypatch.setattr(restore, "_first_index", lambda session: 0)

    assert restore.open_window(_spot(), "/tmp", {}) == ("@7", "")

    new_session = next(c for c in argv if "new-session" in c)
    assert new_session[new_session.index("-x") + 1] == "214"
    assert new_session[new_session.index("-y") + 1] == "67"
    assert ["tmux", "move-window", "-s", "@7", "-t", "=relay:2"] in argv


def test_no_client_falls_back_to_a_usable_size(monkeypatch):
    """Restoring from a script with no attached client must not produce 80x24."""
    monkeypatch.setattr(
        restore.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout="", stderr=""),
    )

    width, height = restore._client_size()
    assert int(width) >= 200
    assert int(height) >= 50


def test_a_first_window_already_at_its_index_is_not_moved(monkeypatch):
    """With base-index 1, tmux makes the first window 1 itself, and refuses to move it there."""
    argv = _recording(monkeypatch)
    monkeypatch.setattr(restore, "_first_index", lambda session: 1)

    assert restore.open_window(_spot("hq", 1), "/tmp", {}) == ("@7", "")
    assert not any("move-window" in a for a in argv)


def test_a_window_in_a_running_session_is_opened_at_its_index(monkeypatch):
    """Even one planned to create the session: an earlier window of it may have made it since."""
    argv = _recording(monkeypatch, sessions=("work",))

    assert restore.open_window(_spot("work", 4, creates=True), "/src", {"A": "1"}) == ("@7", "")

    [opened] = argv
    assert opened[:6] == ["tmux", "new-window", "-d", "-t", "=work:4", "-c"]


def test_a_session_planned_to_exist_is_created_when_it_is_gone(monkeypatch):
    argv = _recording(monkeypatch)
    monkeypatch.setattr(restore, "_first_index", lambda session: 4)

    assert restore.open_window(_spot("work", 4, creates=False), "/src", {}) == ("@7", "")
    assert any("new-session" in a for a in argv)


def test_a_taken_index_is_refused_and_nothing_is_closed(monkeypatch):
    argv = _recording(monkeypatch, fails="new-window", sessions=("work",))

    assert restore.open_window(_spot("work", 4), "/src", {}) == ("", "no")
    assert not any("kill-window" in a for a in argv)


def test_a_session_tmux_would_not_create_says_why(monkeypatch):
    _recording(monkeypatch, fails="new-session")

    assert restore.open_window(_spot(), "/tmp", {})[1].startswith("could not create its session")


def test_the_layout_is_empty_when_no_server_runs(monkeypatch):
    monkeypatch.setattr(
        restore.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 1, stdout="", stderr="no server running"),
    )

    assert restore.layout() == {}


def test_a_restore_that_may_not_start_tmux_makes_a_session_only_on_a_running_server(monkeypatch):
    argv = _recording(monkeypatch)
    monkeypatch.setattr(restore, "_first_index", lambda session: 2)

    restore.open_window(_spot(), "/tmp", {}, start=False)

    new_session = next(c for c in argv if "new-session" in c)
    assert new_session[:3] == ["tmux", "-N", "new-session"]
