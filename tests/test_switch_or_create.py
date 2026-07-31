"""Selecting a session whose pane is gone recreates it instead of failing.

A session's pane disappears whenever its tmux session is killed, which happens
constantly - `:kill-session`, a closed window, a rebooted machine. The archive
still knows where that work was happening, so the cwd is enough to put you back.
"""

from pathlib import Path

from lemonaid import handlers
from lemonaid.config import Config, TmuxSessionConfig

_TEMPLATE = Config(tmux_session=TmuxSessionConfig(templates={"default": ["", "claude", ""]}))


def _no_pane(monkeypatch) -> None:
    monkeypatch.setattr(handlers.tmux.navigation, "get_pane_for_tty", lambda tty: (None, None))
    monkeypatch.setattr(
        handlers.tmux.navigation, "get_pane_for_cwd", lambda cwd, process=None: (None, None)
    )


def _spawns_into(monkeypatch) -> list[dict]:
    spawned: list[dict] = []

    def _spawn(**kwargs):
        spawned.append(kwargs)
        return None  # no error

    monkeypatch.setattr(handlers.tmux.session, "spawn_session", _spawn)
    return spawned


def test_live_pane_is_switched_to_not_respawned(monkeypatch, tmp_path):
    monkeypatch.setattr(handlers.tmux.navigation, "get_pane_for_tty", lambda tty: ("sess", "%3"))
    switched = []
    monkeypatch.setattr(
        handlers.tmux.navigation,
        "switch_to_pane",
        lambda session, pane: switched.append((session, pane)) is None,
    )
    spawned = _spawns_into(monkeypatch)

    assert handlers.handle_notification(
        {"tty": "/dev/ttys001", "cwd": str(tmp_path)}, _TEMPLATE, switch_source="tmux"
    )
    assert switched == [("sess", "%3")]
    assert not spawned


def test_dead_session_respawns_in_its_cwd(monkeypatch, tmp_path):
    _no_pane(monkeypatch)
    spawned = _spawns_into(monkeypatch)

    assert handlers.handle_notification(
        {"tty": "/dev/ttys001", "cwd": str(tmp_path), "name": "old-session"},
        _TEMPLATE,
        switch_source="tmux",
    )
    assert spawned[0]["cwd"] == str(tmp_path)
    assert spawned[0]["session_name"] == "old-session"


def test_no_resume_command_is_passed_when_recreating(monkeypatch, tmp_path):
    """Recreating is not resuming - the template is used as-is."""
    _no_pane(monkeypatch)
    spawned = _spawns_into(monkeypatch)

    handlers.handle_notification({"cwd": str(tmp_path)}, _TEMPLATE, switch_source="tmux")

    assert not spawned[0].get("resume_argv")


def test_vanished_directory_does_not_respawn(monkeypatch, tmp_path):
    """A worktree that has been removed has nowhere to put a session."""
    _no_pane(monkeypatch)
    spawned = _spawns_into(monkeypatch)

    assert not handlers.handle_notification(
        {"cwd": str(tmp_path / "removed-worktree")}, _TEMPLATE, switch_source="tmux"
    )
    assert not spawned


def test_missing_cwd_does_not_respawn(monkeypatch):
    _no_pane(monkeypatch)
    spawned = _spawns_into(monkeypatch)

    assert not handlers.handle_notification(
        {"tty": "/dev/ttys001"}, _TEMPLATE, switch_source="tmux"
    )
    assert not spawned


def test_failed_spawn_is_reported_as_failure(monkeypatch, tmp_path):
    _no_pane(monkeypatch)
    monkeypatch.setattr(
        handlers.tmux.session, "spawn_session", lambda **kwargs: "name already exists"
    )

    assert not handlers.handle_notification({"cwd": str(tmp_path)}, _TEMPLATE, switch_source="tmux")


def test_unnamed_session_gets_a_name_derived_from_its_directory(monkeypatch, tmp_path):
    """The whole spawn path, with only tmux itself stubbed out."""
    _no_pane(monkeypatch)
    created: list[dict] = []
    monkeypatch.setattr(
        handlers.tmux.session,
        "create_session",
        lambda **kwargs: created.append(kwargs) is None or True,
    )
    worktree = tmp_path / "protostellar" / "enums"
    worktree.mkdir(parents=True)

    assert handlers.handle_notification({"cwd": str(worktree)}, _TEMPLATE, switch_source="tmux")

    assert created[0]["name"] == "enums"
    assert created[0]["directory"] == str(worktree)
    assert created[0]["windows"] == ["", "claude", ""]


def test_auto_session_name_uses_two_components_when_short(tmp_path):
    assert (
        handlers.tmux.session.auto_session_name(Path("/Users/x/play/lemonaid")) == "play-lemonaid"
    )


def test_auto_session_name_falls_back_to_one_component(tmp_path):
    assert (
        handlers.tmux.session.auto_session_name(Path("/a/protostellar/tenant-org-identity"))
        == "tenant-org-identity"
    )
