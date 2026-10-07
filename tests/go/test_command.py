import json
import subprocess

import pytest

from lemonaid import go
from lemonaid.inbox import db

from .shared import run


@pytest.mark.parametrize("form", ["id", "channel", "url"])
def test_jump_by_identity_on_recorded_server(target, calls, form):
    value = {"id": target, "channel": "codex:jump", "url": f"lemonaid://go/{target}"}[form]
    run(value)
    assert calls[-1] == [
        "tmux",
        "-S",
        "/test/socket",
        "switch-client",
        "-c",
        "/dev/client",
        "-t",
        "%7",
    ]
    with db.connect() as conn:
        assert db.get_by_channel(conn, "codex:jump").status == "unread"


@pytest.mark.parametrize(
    "pane",
    [
        "%8|/dev/other|work|100|90|$2",  # vanished TTY
        "%8|/dev/target|stranger|100|90|$2",  # reused TTY
        "%7|/dev/target|work|100|91|$2",  # restarted server
        "%8|/dev/target|work|100|90|$2",  # replacement pane in surviving session
    ],
)
def test_stale_pane_never_switches(target, monkeypatch, capsys, pane):
    monkeypatch.setattr(go, "_tmux", lambda command, *args: pane)
    with pytest.raises(SystemExit, match="1"):
        run(target)
    assert "gone or ambiguous" in capsys.readouterr().err


def test_link_is_osc8_and_needs_no_database(capsys):
    run("codex:jump", "--link")
    assert (
        capsys.readouterr().out
        == "\x1b]8;;lemonaid://go/codex%3Ajump\x1b\\codex:jump\x1b]8;;\x1b\\\n"
    )


def test_archived_target_is_rejected(target, calls):
    with db.connect() as conn:
        conn.execute("UPDATE notifications SET status = 'archived'")
        conn.commit()
    with pytest.raises(SystemExit, match="1"):
        run("codex:jump")
    assert not calls


def test_tmux_failure_is_reported(target, monkeypatch, capsys):
    def fail(*args, **kwargs):
        raise subprocess.TimeoutExpired("tmux", 5)

    monkeypatch.setattr(go.subprocess, "run", fail)
    with pytest.raises(SystemExit, match="1"):
        run(target)
    assert "timed out" in capsys.readouterr().err


@pytest.mark.parametrize("missing", ["tty", "tmux_pane_identity", "tmux_session_order"])
def test_old_records_need_a_notification(target, capsys, missing):
    with db.connect() as conn:
        found = db.get_by_channel(conn, "codex:jump")
        metadata = dict(found.metadata)
        metadata.pop(missing)
        conn.execute("UPDATE notifications SET metadata = ?", (json.dumps(metadata),))
        conn.commit()
    with pytest.raises(SystemExit, match="1"):
        run(target)
    assert "wait for its next notification" in capsys.readouterr().err


def test_location_refresh_cannot_bless_old_pane_on_new_server(target, monkeypatch):
    with db.connect() as conn:
        db.record_location(conn, "codex:jump", "work", "0", "/test/socket", (100, 91, 2))
        found = db.get_by_channel(conn, "codex:jump")
    monkeypatch.setattr(go, "_tmux", lambda command, *args: "%7|/dev/target|work|100|91|$2")
    with pytest.raises(LookupError, match="gone or ambiguous"):
        go._pane(["tmux"], found)


def test_notification_without_pane_context_retains_identity(target):
    with db.connect() as conn:
        db.add(conn, "codex:jump", "next", metadata={})
        found = db.get_by_channel(conn, "codex:jump")
    assert found.metadata["tmux_pane_identity"] == ["%7", 90]
