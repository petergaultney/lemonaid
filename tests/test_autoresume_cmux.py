"""A lemon in cmux is found where cmux says it runs, and resumed in a workspace that doesn't take focus."""

import pytest

from lemonaid import handlers
from lemonaid.config import Config
from lemonaid.inbox import db
from lemonaid.messages import autoresume_cmux, autoresume_tmux, recipient, revive


def _row(**metadata) -> db.Notification:
    return db.Notification(
        id=1,
        channel="claude:abc12345",
        message="",
        name="fixing",
        metadata={"cwd": "/tmp", "session_id": "abc12345-full", **metadata},
        switch_source="cmux",
    )


@pytest.mark.parametrize(("found", "alive"), [("/dev/ttys7", True), (False, False), (None, None)])
def test_a_cmux_lemon_is_alive_where_cmux_says_it_runs(monkeypatch, found, alive):
    monkeypatch.setattr(
        handlers, "where_sessions_are", lambda sessions, fresh: {"claude:abc12345": found}
    )

    assert recipient.harness_alive(_row(tty="/dev/ttys1")) is alive


def test_start_opens_an_unfocused_workspace_on_the_wake_prompt(monkeypatch):
    opened: list[tuple] = []
    monkeypatch.setattr(
        autoresume_cmux.navigation,
        "open_workspace",
        lambda cwd, argv, name, focus: opened.append((cwd, argv, name, focus)) or True,
    )

    assert autoresume_cmux.start(_row(), Config()) == ""
    assert opened == [
        (
            "/tmp",
            ["lemonaid", "claude", "resume", "abc12345-full", autoresume_tmux.PROMPT],
            "fixing",
            False,
        )
    ]


def test_an_idle_cmux_lemon_cannot_be_prompted():
    why = revive.bring_back(_row(), False, Config(), autoresume_tmux.PROMPT)

    assert why == "lemonaid can't prompt a lemon in cmux"


def test_another_terminal_gets_the_command_to_resume_by_hand():
    row = db.Notification(
        id=1,
        channel="claude:abc12345",
        message="",
        metadata={"cwd": "/tmp", "session_id": "abc"},
        switch_source="wezterm",
    )

    why = revive.bring_back(row, True, Config(), autoresume_tmux.PROMPT)

    assert why == (
        "lemonaid can't start a lemon in wezterm; it resumes with: "
        "cd /tmp && lemonaid claude resume abc"
    )


def test_a_codex_resumed_in_cmux_gets_the_flags_that_skip_its_startup_dialogs(monkeypatch):
    opened: list[list[str]] = []
    monkeypatch.setattr(
        autoresume_cmux.navigation,
        "open_workspace",
        lambda cwd, argv, name, focus: opened.append(argv) or True,
    )
    row = db.Notification(
        id=1,
        channel="codex:0199",
        message="",
        metadata={"cwd": "/tmp", "session_id": "0199-thread"},
        switch_source="cmux",
    )

    assert autoresume_cmux.start(row, Config()) == ""
    assert opened[0][:2] == ["codex", "-c"]
    assert "check_for_update_on_startup=false" in opened[0]
    assert opened[0][-1] == autoresume_tmux.PROMPT
