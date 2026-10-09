"""Detached rows reuse only a tmux session that can be identified safely."""

from types import SimpleNamespace

from lemonaid.config import Config
from lemonaid.tmux import recreate


def test_recorded_session_identity_wins_over_other_cwd_matches(monkeypatch):
    monkeypatch.setattr(recreate, "_current_socket", lambda: "/tmp/tmux-501/default")
    monkeypatch.setattr(
        recreate,
        "_sessions",
        lambda _socket: {
            "recorded": ((10, 20, 3), "/work/project"),
            "other": ((11, 20, 4), "/work/project"),
        },
    )

    assert recreate._destination(
        {
            "channel": "codex:thread",
            "cwd": "/work/project",
            "tmux_session": "recorded",
            "tmux_session_order": [10, 20, 3],
        }
    ) == ("recorded", "/tmp/tmux-501/default")


def test_unique_cwd_session_is_used_when_recorded_identity_is_gone(monkeypatch):
    monkeypatch.setattr(recreate, "_current_socket", lambda: None)
    monkeypatch.setattr(
        recreate, "_sessions", lambda _socket: {"workspace": ((10, 20, 3), "/other")}
    )
    monkeypatch.setattr(recreate, "_cwd_sessions", lambda _cwd, _socket: {"workspace"})

    assert recreate._destination({"cwd": "/work/project", "tmux_session": "old"}) == (
        "workspace",
        None,
    )


def test_ambiguous_cwd_does_not_choose_a_session(monkeypatch):
    monkeypatch.setattr(recreate, "_current_socket", lambda: None)
    monkeypatch.setattr(
        recreate,
        "_sessions",
        lambda _socket: {
            "one": ((10, 20, 3), "/work/project"),
            "two": ((11, 20, 4), "/other"),
        },
    )
    monkeypatch.setattr(recreate, "_cwd_sessions", lambda _cwd, _socket: {"two"})

    assert recreate._destination({"cwd": "/work/project"}) is None


def test_recorded_other_server_is_not_used(monkeypatch):
    monkeypatch.setattr(recreate, "_current_socket", lambda: "/tmp/tmux-current")

    assert recreate._destination({"cwd": "/work/project", "tmux_socket": "/tmp/tmux-old"}) is None


def test_resume_opens_a_window_in_the_selected_session(monkeypatch):
    calls = []

    monkeypatch.setenv("TMUX", "/tmp/tmux-501/default,1,0")

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(stdout="%42|@7|/dev/ttys009\n")

    monkeypatch.setattr(recreate.subprocess, "run", run)
    monkeypatch.setattr(recreate.navigation, "switch_to_pane", lambda session, pane: True)

    assert (
        recreate._resume_in_session("workspace", None, "/work/project", ["codex", "resume", "id"])
        == "/dev/ttys009"
    )
    assert calls[0][0][1:4] == ["new-window", "-d", "-P"]
    assert calls[0][0][calls[0][0].index("-t") + 1] == "=workspace"
    assert calls[0][0][-1] == "codex resume id"


def test_resume_attaches_to_the_session_when_run_outside_tmux(monkeypatch):
    calls = []
    monkeypatch.delenv("TMUX", raising=False)

    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(stdout="%42|@7|/dev/ttys009\n")

    monkeypatch.setattr(recreate.subprocess, "run", run)
    monkeypatch.setattr(
        recreate.navigation,
        "switch_to_pane",
        lambda *_args: (_ for _ in ()).throw(AssertionError("no tmux client to switch")),
    )

    assert recreate._resume_in_session(
        "workspace", None, "/work/project", ["codex", "resume", "id"]
    )
    assert calls[1][1:] == ["select-window", "-t", "@7"]
    assert calls[2][1:] == ["attach-session", "-t", "=workspace"]


def test_recreate_never_starts_a_new_session_when_destination_is_ambiguous(monkeypatch, tmp_path):
    monkeypatch.setattr(recreate, "_destination", lambda _metadata: None)
    monkeypatch.setattr(
        recreate, "build_resume_command", lambda *_args: (str(tmp_path), ["codex", "resume", "id"])
    )
    calls = []
    monkeypatch.setattr(recreate.subprocess, "run", lambda *args, **kwargs: calls.append(args))

    assert not recreate.recreate({"cwd": str(tmp_path), "channel": "codex:id"}, Config())
    assert calls == []
