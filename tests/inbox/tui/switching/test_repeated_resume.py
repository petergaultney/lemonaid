"""Resuming a stale inbox row records its location before the next selection."""

import subprocess

import pytest

from lemonaid.config import Config
from lemonaid.inbox import db, resume_archived
from lemonaid.inbox.tui.switching import inbox_switch


@pytest.mark.parametrize("pane_identity", [None, ["%1", 10]])
def test_selecting_twice_resumes_once(monkeypatch, tmp_path, pane_identity):
    tmux = resume_archived.tmux
    metadata = {
        "tty": "/dev/old",
        "cwd": str(tmp_path),
        "session_id": "thread",
        "tmux_session": "original",
        "tmux_session_order": [100, 10, 3],
    }
    if pane_identity:
        metadata["tmux_pane_identity"] = pane_identity
    with db.connect() as conn:
        notification = db.add(
            conn, "codex:thread", "ready", "original", metadata, switch_source="tmux"
        )

    resumed = []
    switched = []
    monkeypatch.setattr(tmux.recreate, "resume", lambda *args: resumed.append(args) or "/dev/new")
    monkeypatch.setattr(
        tmux.navigation,
        "locations_by_tty",
        lambda *args: {"/dev/new": tmux.navigation.PaneLocation("original", "4", (100, 10, 3))},
    )
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda argv, **kwargs: subprocess.CompletedProcess(
            argv, 0, stdout="%9|/dev/new|original|100|10|$3"
        ),
    )
    monkeypatch.setattr(
        tmux.navigation, "switch_to_pane", lambda *args: switched.append(args) or True
    )

    for _ in range(2):
        assert inbox_switch.switch_to(
            None, notification, Config(), lambda _: pytest.fail("archive")
        )

    assert len(resumed) == 1
    assert switched == [("original", "%9")]
    with db.connect() as conn:
        saved = db.get(conn, notification.id)
    assert saved.metadata == notification.metadata
    assert saved.metadata["tty"] == "/dev/new"
    assert saved.metadata["tmux_window"] == "4"
    assert saved.metadata["tmux_session_order"] == [100, 10, 3]
    assert "tmux_pane_identity" not in saved.metadata
    assert saved.status == notification.status
