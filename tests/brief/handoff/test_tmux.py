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


def test_rearm_prompt_requires_the_original_pane_and_command(setup, monkeypatch):
    conn, path = setup
    row = requested(conn, path)
    monkeypatch.setattr(handoff_tmux, "pane", lambda *_: ("%different", "@2"))
    assert not handoff_tmux.prompt_source_to_rearm(row, "timed out")

    monkeypatch.setattr(handoff_tmux, "pane", lambda *_: ("%2", "@2"))
    monkeypatch.setattr(handoff_tmux, "current_command", lambda *_: "zsh")
    assert not handoff_tmux.prompt_source_to_rearm(row, "timed out")


def test_rearm_prompt_is_sent_to_the_checked_source_pane(setup, monkeypatch):
    conn, path = setup
    row = requested(conn, path)
    monkeypatch.setattr(handoff_tmux, "pane", lambda *_: ("%2", "@2"))
    monkeypatch.setattr(handoff_tmux, "current_command", lambda *_: "claude")
    calls = []
    monkeypatch.setattr(
        handoff_tmux.time, "sleep", lambda seconds: calls.append(["pause", seconds])
    )

    def run(args, **_kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(handoff_tmux.subprocess, "run", run)
    assert handoff_tmux.prompt_source_to_rearm(row, "timed out")
    assert calls[0][:5] == ["tmux", "send-keys", "-t", "%2", "-l"]
    assert "Rearm `lemonaid inbox watch --self`" in calls[0][5]
    assert calls[1] == ["pause", 1]
    assert calls[2] == ["tmux", "send-keys", "-t", "%2", "Enter"]
