"""Judging which rows lost their lemon with their tmux server."""

import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import pytest

from lemonaid import tmux
from lemonaid.front_end import tmux as tmux_front_end
from lemonaid.inbox import db, ended
from lemonaid.inbox.tui.watchers import watcher_hooks
from lemonaid.restore import cli, loss

_SOCKET = "/tmp/recorded/default"


def _row(channel: str, **metadata: object) -> None:
    with db.connect() as conn:
        db.add(
            conn,
            channel,
            "waiting",
            metadata={"tty": f"/dev/{channel}", "cwd": "/tmp", **metadata},
            upsert=False,
            switch_source="tmux",
        )


def _causes() -> dict[str, tuple[str, str]]:
    with db.connect() as conn:
        return {
            row["channel"]: (row["status"], ended.cause(json.loads(row["metadata"])))
            for row in conn.execute("SELECT channel, status, metadata FROM notifications")
        }


@pytest.mark.parametrize(
    ("server", "order", "verdict"),
    [
        pytest.param(tmux.server.GONE, [5, 100, 1], True, id="no-server"),
        pytest.param(tmux.server.GONE, None, True, id="no-server-no-order"),
        pytest.param(200, [5, 100, 1], True, id="newer-server"),
        pytest.param(100, [5, 100, 1], False, id="same-server"),
        pytest.param(200, None, None, id="running-server-no-order"),
        pytest.param(None, [5, 100, 1], None, id="tmux-did-not-answer"),
    ],
)
def test_a_row_is_lost_only_when_its_server_is_gone_or_replaced(
    monkeypatch, server, order, verdict
):
    monkeypatch.setattr(tmux.server, "started", lambda socket: server)
    metadata = {"tmux_socket": _SOCKET, **({"tmux_session_order": order} if order else {})}

    assert tmux_front_end.lost([metadata]) == [verdict]


def test_a_row_with_no_recorded_socket_is_never_judged(monkeypatch):
    monkeypatch.setattr(tmux.server, "started", lambda socket: tmux.server.GONE)

    assert tmux_front_end.lost([{"tmux_session_order": [5, 100, 1]}]) == [None]


def test_marking_keeps_lost_rows_active_and_archives_those_that_ended_themselves(monkeypatch):
    monkeypatch.setattr(tmux.server, "started", lambda socket: 200)
    order = {"tmux_socket": _SOCKET, "tmux_session_order": [5, 100, 1]}
    _row("claude:lost", **order)
    _row("claude:exited", **order, exit_reason="prompt_input_exit", exited_at=1.0)
    _row("claude:cleared", **order, exit_reason="clear", exited_at=1.0)
    _row("claude:here", tmux_socket=_SOCKET, tmux_session_order=[150, 200, 2])

    with db.connect() as conn:
        marked = loss.mark(conn, by="test")
        again = loss.mark(conn, by="test")

    assert [row.channel for row in marked] == ["claude:lost"]
    assert again == []
    assert _causes() == {
        "claude:lost": ("unread", ended.SERVER_LOST),
        "claude:exited": ("archived", ended.USER_EXIT),
        "claude:cleared": ("archived", ended.REPLACED),
        "claude:here": ("unread", ""),
    }


def test_a_lost_row_recorded_again_on_the_running_server_is_lost_no_longer(monkeypatch):
    monkeypatch.setattr(tmux.server, "started", lambda socket: 200)
    _row("claude:moved", tmux_socket=_SOCKET, tmux_session_order=[5, 100, 1])
    with db.connect() as conn:
        loss.mark(conn, by="test")
        row = db.get_by_channel(conn, "claude:moved", unread_only=False)
        assert row is not None
        db.repair_location(conn, row, {"tmux_session_order": [150, 200, 2]})
        loss.mark(conn, by="test")

    assert _causes()["claude:moved"] == ("unread", "")


def test_the_server_on_a_socket_is_told_from_none_at_all():
    if not shutil.which("tmux"):
        pytest.skip("tmux is not installed")
    socket = str(Path(tempfile.mkdtemp(prefix="lma-srv-", dir="/tmp")) / "s")

    assert tmux.server.started(socket) == tmux.server.GONE
    subprocess.run(["tmux", "-S", socket, "-f", "/dev/null", "new-session", "-d"], check=True)
    try:
        assert isinstance(tmux.server.started(socket), int)
    finally:
        subprocess.run(["tmux", "-S", socket, "kill-server"], check=False)
    deadline = time.monotonic() + 5  # a server still shutting down "exited unexpectedly"
    while (now := tmux.server.started(socket)) is None and time.monotonic() < deadline:
        time.sleep(0.05)
    assert now == tmux.server.GONE


def test_a_snoozed_lemon_is_lost_with_its_server_and_restorable(monkeypatch):
    monkeypatch.setattr(tmux.server, "started", lambda socket: tmux.server.GONE)
    _row("claude:snoozed", tmux_socket=_SOCKET)
    with db.connect() as conn:
        row = db.get_by_channel(conn, "claude:snoozed", unread_only=False)
        assert row is not None
        db.snooze(conn, row.id, time.time() + 3600)

        marked = loss.mark(conn, by="test")

    assert [r.channel for r in marked] == ["claude:snoozed"]
    assert _causes()["claude:snoozed"] == ("snoozed", ended.SERVER_LOST)
    assert [r.channel for r in cli._lost(dry_run=True)] == ["claude:snoozed"]


@pytest.mark.parametrize("reason", ["prompt_input_exit", "clear"])
def test_a_dry_run_leaves_out_the_lemons_a_real_run_archives(monkeypatch, reason):
    monkeypatch.setattr(tmux.server, "started", lambda socket: tmux.server.GONE)
    _row("claude:lost", tmux_socket=_SOCKET)
    _row("claude:ended", tmux_socket=_SOCKET, exit_reason=reason, exited_at=1.0)

    planned = [r.channel for r in cli._lost(dry_run=True)]

    assert planned == [r.channel for r in cli._lost(dry_run=False)] == ["claude:lost"]


@pytest.mark.parametrize(
    ("server", "expected"),
    [
        pytest.param(tmux.server.GONE, ("unread", ended.SERVER_LOST), id="server-gone"),
        pytest.param(100, ("archived", ended.PANE_CLOSED), id="server-running"),
    ],
)
def test_the_watcher_marks_a_row_lost_rather_than_archive_it_between_loss_checks(
    monkeypatch, server, expected
):
    _row("claude:a", tmux_socket=_SOCKET, tmux_session_order=[5, 100, 1])
    monkeypatch.setattr(tmux.server, "started", lambda socket: server)

    watcher_hooks.archive_channel("claude:a", "pane-gone tty=/dev/claude:a")

    assert _causes()["claude:a"] == expected


def test_a_lemon_that_ended_itself_before_its_server_went_is_audited_as_archived(monkeypatch):
    _row("claude:a", tmux_socket=_SOCKET, tmux_session_order=[5, 100, 1], exit_reason="clear")
    monkeypatch.setattr(tmux.server, "started", lambda socket: tmux.server.GONE)
    recorded: list[str] = []
    monkeypatch.setattr(
        watcher_hooks.events, "record", lambda kind, *args, **kwargs: recorded.append(kind)
    )

    watcher_hooks.archive_channel("claude:a", "pane-gone tty=/dev/claude:a")

    assert _causes()["claude:a"] == ("archived", ended.REPLACED)
    assert recorded == ["inbox-archive"]
