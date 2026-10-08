"""Selecting a detached row resumes it only in a safe existing tmux session."""

from pathlib import Path

from lemonaid import handlers
from lemonaid.config import Config

_CONFIG = Config()


def _no_pane(monkeypatch) -> None:
    monkeypatch.setattr(handlers.tmux.navigation, "get_pane_for_tty", lambda tty: (None, None))
    monkeypatch.setattr(
        handlers.tmux.navigation, "get_pane_for_cwd", lambda cwd, process=None: (None, None)
    )
    monkeypatch.setattr(
        handlers.tmux.recreate, "_destination", lambda _metadata: ("existing", None)
    )


def _row(cwd, **extra) -> dict[str, str]:
    return {"channel": "claude:abc", "session_id": "abc", "cwd": str(cwd), **extra}


def _resumes_into(monkeypatch) -> list[tuple]:
    resumed: list[tuple] = []

    def _resume(session, socket, cwd, argv):
        resumed.append((session, socket, cwd, argv))
        return True

    monkeypatch.setattr(handlers.tmux.recreate, "_resume_in_session", _resume)
    return resumed


def test_live_pane_is_switched_to_not_respawned(monkeypatch, tmp_path):
    monkeypatch.setattr(handlers.tmux.navigation, "get_pane_for_tty", lambda tty: ("sess", "%3"))
    switched = []
    monkeypatch.setattr(
        handlers.tmux.navigation,
        "switch_to_pane",
        lambda session, pane: switched.append((session, pane)) is None,
    )
    resumed = _resumes_into(monkeypatch)

    assert handlers.handle_notification(
        {"tty": "/dev/ttys001", "cwd": str(tmp_path)}, _CONFIG, switch_source="tmux"
    )
    assert switched == [("sess", "%3")]
    assert not resumed


def test_dead_session_resumes_in_an_existing_tmux_session(monkeypatch, tmp_path):
    _no_pane(monkeypatch)
    resumed = _resumes_into(monkeypatch)

    assert handlers.handle_notification(
        _row(tmp_path, tty="/dev/ttys001", name="old-session"),
        _CONFIG,
        switch_source="tmux",
    )
    assert resumed == [("existing", None, str(tmp_path), ["lemonaid", "claude", "resume", "abc"])]


def test_recreating_resumes_the_rows_own_session(monkeypatch, tmp_path):
    _no_pane(monkeypatch)
    resumed = _resumes_into(monkeypatch)

    handlers.handle_notification(_row(tmp_path), _CONFIG, switch_source="tmux")

    assert resumed == [("existing", None, str(tmp_path), ["lemonaid", "claude", "resume", "abc"])]


def test_a_codex_row_uses_its_backend_resume_command(monkeypatch, tmp_path):
    _no_pane(monkeypatch)
    resumed = _resumes_into(monkeypatch)

    handlers.handle_notification(
        {"channel": "codex:0199", "session_id": "0199", "cwd": str(tmp_path)},
        _CONFIG,
        switch_source="tmux",
    )

    assert resumed == [("existing", None, str(tmp_path), ["codex", "resume", "0199"])]


def test_a_row_that_cannot_be_resumed_is_not_recreated(monkeypatch, tmp_path):
    """No session id means no resume command, and the template alone would start a stranger."""
    _no_pane(monkeypatch)
    resumed = _resumes_into(monkeypatch)

    assert not handlers.handle_notification(
        {"channel": "codex:0199", "cwd": str(tmp_path)}, _CONFIG, switch_source="tmux"
    )
    assert not resumed


def test_no_safe_destination_does_not_resume_in_another_session(monkeypatch, tmp_path):
    _no_pane(monkeypatch)
    monkeypatch.setattr(handlers.tmux.recreate, "_destination", lambda _metadata: None)
    resumed = _resumes_into(monkeypatch)

    assert not handlers.handle_notification(
        _row(tmp_path, name="old-session"), _CONFIG, switch_source="tmux"
    )
    assert not resumed


def test_vanished_directory_resumes_in_surviving_parent(monkeypatch, tmp_path):
    _no_pane(monkeypatch)
    resumed = _resumes_into(monkeypatch)

    assert handlers.handle_notification(
        _row(tmp_path / "removed-worktree"), _CONFIG, switch_source="tmux"
    )
    assert resumed == [("existing", None, str(tmp_path), ["lemonaid", "claude", "resume", "abc"])]


def test_missing_cwd_does_not_respawn(monkeypatch):
    _no_pane(monkeypatch)
    resumed = _resumes_into(monkeypatch)

    assert not handlers.handle_notification({"tty": "/dev/ttys001"}, _CONFIG, switch_source="tmux")
    assert not resumed


def test_failed_resume_in_existing_session_is_reported_as_failure(monkeypatch, tmp_path):
    _no_pane(monkeypatch)
    monkeypatch.setattr(handlers.tmux.recreate, "_resume_in_session", lambda *args: False)

    assert not handlers.handle_notification(_row(tmp_path), _CONFIG, switch_source="tmux")


def test_auto_session_name_uses_two_components_when_short(tmp_path):
    assert (
        handlers.tmux.session.auto_session_name(Path("/Users/x/play/lemonaid")) == "play-lemonaid"
    )


def test_auto_session_name_falls_back_to_one_component(tmp_path):
    assert (
        handlers.tmux.session.auto_session_name(Path("/a/protostellar/tenant-org-identity"))
        == "tenant-org-identity"
    )


def test_missing_codex_directory_passes_explicit_working_directory(monkeypatch, tmp_path):
    _no_pane(monkeypatch)
    resumed = _resumes_into(monkeypatch)
    assert handlers.handle_notification(
        {"channel": "codex:id", "session_id": "id", "cwd": str(tmp_path / "gone")},
        _CONFIG,
        switch_source="tmux",
    )
    assert resumed == [
        ("existing", None, str(tmp_path), ["codex", "resume", "id", "--cd", str(tmp_path)])
    ]
