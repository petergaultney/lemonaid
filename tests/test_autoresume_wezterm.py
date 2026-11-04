"""Bringing a lemon back goes to the WezTerm instance and workspace it was recorded in."""

import json
import subprocess
import types

import pytest

from lemonaid.config import BackendConfig, Config
from lemonaid.inbox import db
from lemonaid.messages import autoresume_wezterm, revive, wake
from lemonaid.wezterm import client, location

_IDLE = "✻ Worked for 8s\n\n────────\n\u276f \n────────\n  status line\n"
_DIALOG = "Do you want to proceed?\n\u276f 1. Yes\n  2. No\n"


def _row(**metadata) -> db.Notification:
    return db.Notification(
        id=1,
        channel="claude:abc12345",
        message="",
        metadata={"wezterm_socket": "/tmp/gui-sock", "session_id": "abc12345-full", **metadata},
        switch_source="wezterm",
    )


@pytest.fixture
def wezterm(monkeypatch) -> types.SimpleNamespace:
    """Every `wezterm cli` command run, answered as an instance with `panes` would."""
    seen = types.SimpleNamespace(calls=[], sockets=set(), screen=_IDLE, panes=[])

    def run(args, socket=None):
        seen.calls.append(list(args))
        seen.sockets.add(socket)
        out = {
            "list": json.dumps(seen.panes),
            "spawn": "42\n",
            "get-text": seen.screen,
        }.get(args[0], "")
        return subprocess.CompletedProcess(args, 0, out, "")

    monkeypatch.setattr(client, "run", run)
    monkeypatch.setattr(autoresume_wezterm.time, "sleep", lambda seconds: None)
    seen.running = {"abc12345-full": {"/dev/ttys5"}}
    monkeypatch.setattr(autoresume_wezterm.owners, "running", lambda: seen.running)
    return seen


def _spawned(wezterm) -> list[str]:
    return next(call for call in wezterm.calls if call[0] == "spawn")


def test_start_opens_a_tab_in_a_window_of_its_workspace_and_types_the_resume(wezterm, tmp_path):
    wezterm.panes = [
        {"pane_id": 1, "window_id": 3, "workspace": "other"},
        {"pane_id": 2, "window_id": 7, "workspace": "feat-x"},
    ]

    assert (
        autoresume_wezterm.start(_row(wezterm_workspace="feat-x", cwd=str(tmp_path)), Config())
        == ""
    )

    spawn = _spawned(wezterm)
    assert spawn[:5] == ["spawn", "--window-id", "7", "--cwd", str(tmp_path)]
    assert spawn[5:7] == ["--", "env"]
    assert any(arg.startswith("LEMONAID_PROMPT=") for arg in spawn)
    typed = wezterm.calls[-1]
    assert typed[:4] == ["send-text", "--no-paste", "--pane-id", "42"]
    assert "lemonaid claude resume abc12345-full" in typed[4]
    assert typed[4].endswith("\r")
    assert wezterm.sockets == {"/tmp/gui-sock"}


def test_start_recreates_a_workspace_that_is_gone(wezterm, tmp_path):
    assert (
        autoresume_wezterm.start(_row(wezterm_workspace="feat-x", cwd=str(tmp_path)), Config())
        == ""
    )

    assert _spawned(wezterm)[:4] == ["spawn", "--new-window", "--workspace", "feat-x"]


def test_start_without_a_recorded_workspace_says_so(wezterm):
    assert autoresume_wezterm.start(_row(cwd="/tmp"), Config()) == (
        "no WezTerm workspace is recorded for it"
    )
    assert wezterm.calls == []


@pytest.mark.parametrize(("key", "sent"), [("Enter", "\r"), ("C-Enter", "\x1b[13;5u")])
def test_prompt_types_and_submits_in_the_pane_on_its_recorded_tty(wezterm, key, sent):
    wezterm.panes = [{"pane_id": 9, "window_id": 1, "workspace": "w", "tty_name": "/dev/ttys5"}]
    config = Config(backends={"claude": BackendConfig(submit_key=key)})

    assert autoresume_wezterm.prompt(_row(tty="/dev/ttys5"), config) == ""

    sent_text = [call for call in wezterm.calls if call[0] == "send-text"]
    assert sent_text == [
        ["send-text", "--no-paste", "--pane-id", "9", wake.PROMPT],
        ["send-text", "--no-paste", "--pane-id", "9", sent],
    ]


def test_prompt_refuses_a_pane_showing_a_dialog(wezterm):
    wezterm.panes = [{"pane_id": 9, "window_id": 1, "workspace": "w", "tty_name": "/dev/ttys5"}]
    wezterm.screen = _DIALOG

    assert "doesn't show an empty prompt" in autoresume_wezterm.prompt(
        _row(tty="/dev/ttys5"), Config()
    )
    assert not [call for call in wezterm.calls if call[0] == "send-text"]


def test_prompt_never_types_into_a_terminal_another_lemon_runs_in(wezterm):
    wezterm.panes = [{"pane_id": 9, "window_id": 1, "workspace": "w", "tty_name": "/dev/ttys5"}]
    wezterm.running = {"other-lemon": {"/dev/ttys5"}}

    assert "runs another lemon" in autoresume_wezterm.prompt(_row(tty="/dev/ttys5"), Config())
    assert not [call for call in wezterm.calls if call[0] == "send-text"]


def test_bring_back_sends_a_wezterm_lemon_through_wezterm(monkeypatch):
    monkeypatch.setattr(autoresume_wezterm, "start", lambda row, config, text: "started")

    assert revive.bring_back(_row(), True, Config(), "hi") == "started"


def test_location_records_the_hooks_pane_workspace_and_instance(wezterm, monkeypatch):
    wezterm.panes = [{"pane_id": 4, "window_id": 1, "workspace": "feat-x"}]
    monkeypatch.setenv("WEZTERM_PANE", "4")
    monkeypatch.setenv("WEZTERM_UNIX_SOCKET", "/tmp/gui-sock")

    assert location.metadata() == {
        "wezterm_pane": 4,
        "wezterm_workspace": "feat-x",
        "wezterm_socket": "/tmp/gui-sock",
    }


def test_location_outside_wezterm_is_empty(wezterm, monkeypatch):
    monkeypatch.delenv("WEZTERM_PANE", raising=False)

    assert location.metadata() == {}
    assert wezterm.calls == []
