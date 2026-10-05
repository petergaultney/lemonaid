"""Old tmux window teardown requires current positive evidence."""

import subprocess

from lemonaid.brief import handoff_coordinator, handoff_state, handoff_tmux

from .shared import requested


def test_tmux_query_failure_keeps_cleanup_pending(setup, monkeypatch):
    conn, path = setup
    row = requested(conn, path)
    conn.execute("UPDATE brief_handoffs SET phase = 'transferred' WHERE token = ?", (row["token"],))
    conn.commit()
    monkeypatch.setattr(
        handoff_tmux.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 1, "", "server unavailable"),
    )
    assert "old pane changed" in handoff_coordinator.advance(conn, row["token"])["missing"][0]
    assert handoff_state.get(conn, row["token"])["phase"] == "transferred"


def test_replaced_command_in_same_pane_is_not_closed(setup, monkeypatch):
    conn, path = setup
    row = requested(conn, path)

    def run(args, **_kwargs):
        if "list-windows" in args:
            return subprocess.CompletedProcess(args, 0, "@2\n", "")
        if "list-panes" in args:
            return subprocess.CompletedProcess(args, 0, "%2\tzsh\t0\n", "")
        raise AssertionError("kill-window must not run")

    monkeypatch.setattr(handoff_tmux.subprocess, "run", run)
    assert not handoff_tmux.close_old(row)
