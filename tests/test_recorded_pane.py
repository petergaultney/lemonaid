"""Inbox jumps must not follow a tty inherited by another session."""

import subprocess

import pytest

from lemonaid import handlers
from lemonaid.config import Config


@pytest.mark.parametrize(
    "identity, live",
    [
        ({"tmux_session": "original"}, "%9|/dev/ttys081|other|100|10|$4"),
        ({"tmux_session_order": [100, 10, 3]}, "%9|/dev/ttys081|original|100|10|$4"),
        ({"tmux_pane_identity": ["%3", 10]}, "%9|/dev/ttys081|original|100|10|$3"),
        ({"tmux_pane_identity": ["%3", 10]}, "%3|/dev/ttys081|original|100|20|$3"),
    ],
)
def test_stale_location_resumes_instead_of_switching(monkeypatch, identity, live):
    calls = []

    def run(argv, **kwargs):
        assert "list-panes" in argv
        return subprocess.CompletedProcess(argv, 0, stdout=live)

    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(
        handlers.tmux.navigation, "switch_to_pane", lambda *args: pytest.fail("wrong lemon")
    )
    monkeypatch.setattr(
        handlers.tmux.navigation,
        "get_pane_for_cwd",
        lambda *args: pytest.fail("cwd is not identity"),
    )
    monkeypatch.setattr(
        handlers.tmux.recreate, "recreate", lambda metadata, config: calls.append(metadata) is None
    )
    metadata = {"tty": "/dev/ttys081", "cwd": "/work/shared", "channel": "codex:old", **identity}

    assert handlers.handle_notification(metadata, Config(), switch_source="tmux")
    assert calls == [metadata]


def test_matching_recorded_location_switches(monkeypatch):
    calls = []
    monkeypatch.setenv("TMUX", "/tmp/test-socket,1,0")

    def run(argv, **kwargs):
        assert argv[:3] == ["tmux", "-S", "/tmp/test-socket"]
        return subprocess.CompletedProcess(argv, 0, stdout="%3|/dev/ttys081|original|100|10|$3")

    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(
        handlers.tmux.navigation, "switch_to_pane", lambda *args: calls.append(args) is None
    )
    metadata = {
        "tty": "/dev/ttys081",
        "tmux_socket": "/tmp/test-socket",
        "tmux_session": "original",
        "tmux_session_order": [100, 10, 3],
        "tmux_pane_identity": ["%3", 10],
    }

    assert handlers.handle_notification(metadata, Config(), switch_source="tmux")
    assert calls == [("original", "%3")]


def test_a_renamed_session_still_switches(monkeypatch):
    """tmux keeps a session's id through a rename, and the recorded order holds that id."""
    calls = []
    monkeypatch.setenv("TMUX", "/tmp/test-socket,1,0")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda argv, **kwargs: subprocess.CompletedProcess(
            argv, 0, stdout="%3|/dev/ttys081|renamed|100|10|$3"
        ),
    )
    monkeypatch.setattr(
        handlers.tmux.navigation, "switch_to_pane", lambda *args: calls.append(args) is None
    )
    metadata = {
        "tty": "/dev/ttys081",
        "tmux_socket": "/tmp/test-socket",
        "tmux_session": "original",
        "tmux_session_order": [100, 10, 3],
        "tmux_pane_identity": ["%3", 10],
    }

    assert handlers.handle_notification(metadata, Config(), switch_source="tmux")
    assert calls == [("renamed", "%3")]


@pytest.mark.parametrize("unavailable", ["other-server", "query-failed"])
def test_unknown_location_neither_switches_nor_resumes(monkeypatch, unavailable):
    monkeypatch.setenv("TMUX", "/tmp/current,1,0")

    def run(argv, **kwargs):
        raise subprocess.CalledProcessError(1, argv)

    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(
        handlers.tmux.navigation, "switch_to_pane", lambda *args: pytest.fail("switch")
    )
    monkeypatch.setattr(handlers.tmux.recreate, "recreate", lambda *args: pytest.fail("resume"))

    assert not handlers.handle_notification(
        {
            "tty": "/dev/ttys081",
            "tmux_session": "original",
            "tmux_socket": "/tmp/other" if unavailable == "other-server" else "/tmp/current",
        },
        Config(),
        switch_source="tmux",
    )


def test_recorded_pane_still_switches_after_hook_loses_tty(monkeypatch):
    calls = []
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda argv, **kwargs: subprocess.CompletedProcess(
            argv, 0, stdout="%3|/dev/ttys081|original|100|10|$3"
        ),
    )
    monkeypatch.setattr(
        handlers.tmux.navigation, "switch_to_pane", lambda *args: calls.append(args) is None
    )
    monkeypatch.setattr(handlers.tmux.recreate, "recreate", lambda *args: pytest.fail("resume"))

    assert handlers.handle_notification(
        {
            "tmux_session": "original",
            "tmux_session_order": [100, 10, 3],
            "tmux_pane_identity": ["%3", 10],
        },
        Config(),
        switch_source="tmux",
    )
    assert calls == [("original", "%3")]


@pytest.mark.parametrize(
    "live",
    [
        "%9|/dev/ttys081|original|100|10|$3",
        "%3|/dev/ttys081|original|100|20|$3",
        "%3|/dev/ttys081|replacement|200|10|$4",
    ],
)
def test_missing_tty_does_not_allow_replacement_identity(monkeypatch, live):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda argv, **kwargs: subprocess.CompletedProcess(argv, 0, stdout=live),
    )
    assert handlers.tmux.recorded_pane.locate(
        {
            "tmux_session": "original",
            "tmux_session_order": [100, 10, 3],
            "tmux_pane_identity": ["%3", 10],
        }
    ) == (None, None)
