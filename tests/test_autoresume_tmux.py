"""Bringing a lemon back goes to the tmux server it was recorded on, and never types into a dialog."""

import subprocess
import types

import pytest

from lemonaid import messages_config
from lemonaid.config import Config
from lemonaid.inbox import db
from lemonaid.messages import autoresume_tmux

_IDLE = "✻ Worked for 8s\n\n────────\n\u276f \n────────\n  status line\n"
_DIALOG = "Do you want to proceed?\n\u276f 1. Yes\n  2. No\n"


def _row(**metadata) -> db.Notification:
    return db.Notification(
        id=1,
        channel="claude:abc12345",
        message="",
        metadata={"tmux_socket": "/tmp/other.sock", **metadata},
    )


@pytest.fixture
def tmux(monkeypatch) -> types.SimpleNamespace:
    """Every tmux command run, answered as a server showing `screen` would."""
    seen = types.SimpleNamespace(calls=[], screen=_IDLE)

    def run(argv, **kwargs):
        seen.calls.append(argv)
        out = {"new-window": "%9\n", "capture-pane": seen.screen}.get(argv[3], "")
        return subprocess.CompletedProcess(argv, 0, out, "")

    monkeypatch.setattr(autoresume_tmux.subprocess, "run", run)
    monkeypatch.setattr(autoresume_tmux.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        autoresume_tmux.navigation, "get_pane_for_tty", lambda tty, socket: ("work", "%3")
    )
    return seen


def test_start_opens_a_window_on_the_recorded_server_and_types_the_resume(tmux, tmp_path):
    why = autoresume_tmux.start(
        _row(tmux_session="work", cwd=str(tmp_path), session_id="abc12345-full"), Config()
    )

    assert why == ""
    assert tmux.calls[0][:6] == ["tmux", "-S", "/tmp/other.sock", "new-window", "-d", "-t"]
    assert tmux.calls[0][6] == "=work:"
    assert tmux.calls[1][:6] == ["tmux", "-S", "/tmp/other.sock", "send-keys", "-t", "%9"]
    assert "lemonaid claude resume abc12345-full" in tmux.calls[1][6]


def test_start_without_a_recorded_session_says_so():
    assert autoresume_tmux.start(_row(cwd="/tmp"), Config()) == "no tmux session is recorded for it"


def test_prompt_types_and_submits_in_the_recorded_pane_on_its_server(tmux):
    assert autoresume_tmux.prompt(_row(tty="/dev/ttys5"), Config()) == ""

    sent = [call for call in tmux.calls if call[3] == "send-keys"]
    assert all(
        call[:6] == ["tmux", "-S", "/tmp/other.sock", "send-keys", "-t", "%3"] for call in sent
    )
    assert sent[0][6:] == ["-l", autoresume_tmux.PROMPT]
    assert sent[1][6:] == ["Enter"]


def test_prompt_refuses_a_pane_showing_a_dialog(tmux):
    tmux.screen = _DIALOG

    why = autoresume_tmux.prompt(_row(tty="/dev/ttys5"), Config())

    assert "doesn't show an empty prompt" in why
    assert not [call for call in tmux.calls if call[3] == "send-keys"]


@pytest.mark.parametrize(
    ("screen", "ready"),
    [(_IDLE, True), (_DIALOG, False), ("\u276f half a draft\n", False), ("$ \n", False)],
)
def test_ready_for_input(screen, ready):
    assert autoresume_tmux.ready_for_input(screen) is ready


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("on", {"claude", "codex"}),
        ("off", set()),
        ("claude", {"claude"}),
        (False, set()),
        ("sometimes", {"claude", "codex"}),
    ],
)
def test_autoresume_setting(raw, expected):
    assert messages_config.parse({"autoresume": raw}).autoresume == expected
