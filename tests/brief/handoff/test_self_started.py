"""A sender in a pane stops before an OpenClaw receiver starts, and comes back only while no
receiver can be running."""

import time

import pytest

from lemonaid.brief.handoff import coordinator as handoff_coordinator
from lemonaid.brief.handoff import pane as handoff_tmux
from lemonaid.brief.handoff import self_started
from lemonaid.brief.handoff import state as handoff_state
from lemonaid.openclaw import gateway, sync


@pytest.fixture
def ready(setup, monkeypatch, tmp_path):
    """A handoff from claude:old in pane %2 to OpenClaw, its brief marked ready, with fake
    pane and gateway calls recorded in order."""
    conn, path = setup
    calls: list[str] = []
    monkeypatch.setattr(
        sync, "agents", lambda cli: {"main": sync.Agent("main", "Ada", str(tmp_path), True)}
    )
    monkeypatch.setattr(handoff_tmux, "has_pane", lambda *_: True)
    monkeypatch.setattr(self_started, "_stop_sender", lambda *_: calls.append("hold") or "4242")
    monkeypatch.setattr(
        handoff_tmux, "resume_source", lambda conn, row: calls.append("resume") or True
    )
    row = handoff_state.request(
        conn, path, "claude:old", "openclaw", "work", "2", "@2", "%2", "claude", time.time() + 600
    )
    conn.execute(
        "UPDATE brief_handoffs SET resume_line = 'claude --resume old', resume_cwd = ?"
        " WHERE token = ?",
        (str(tmp_path), row["token"]),
    )
    conn.commit()
    path.write_text(
        path.read_text().replace("Old notes.", f"Notes.\nHandoff-Ready: {row['token']}")
    )
    return conn, row["token"], calls


def _gateway(monkeypatch, calls: list[str], fails: str) -> None:
    def call(cli, method, params, timeout):
        calls.append(method)
        if method == fails:
            raise OSError(f"{method} failed")
        return {"sessionId": "s"}

    monkeypatch.setattr(gateway, "call", call)


def _fail(conn, token: str) -> str:
    with pytest.raises(OSError):
        handoff_coordinator.advance(conn, token)
    return handoff_coordinator.recover_source(conn, handoff_state.get(conn, token), "failed")


def test_a_sender_that_will_not_stop_never_gets_a_receiver(ready, monkeypatch):
    conn, token, calls = ready
    _gateway(monkeypatch, calls, fails="")

    def stuck(*_):
        raise TimeoutError("PID 7 did not exit after SIGTERM; no replacement started")

    monkeypatch.setattr(self_started, "_stop_sender", stuck)

    with pytest.raises(TimeoutError, match="did not exit"):
        handoff_coordinator.advance(conn, token)

    assert calls == []


def test_a_receiver_that_never_started_resumes_the_sender(ready, monkeypatch):
    conn, token, calls = ready
    _gateway(monkeypatch, calls, fails="sessions.create")

    error = _fail(conn, token)

    assert calls == ["hold", "sessions.create", "resume"]
    assert "resumed in its original pane" in error


def test_a_receiver_that_may_be_running_leaves_the_sender_stopped(ready, monkeypatch, tmp_path):
    conn, token, calls = ready
    _gateway(monkeypatch, calls, fails="chat.send")

    error = _fail(conn, token)

    assert calls == ["hold", "sessions.create", "chat.send"]
    assert "may be running" in error
    assert f"cd {tmp_path} && claude --resume old" in error
    assert handoff_state.get(conn, token)["phase"] == "failed"


def test_a_timeout_after_the_receiver_started_leaves_the_sender_stopped(ready, monkeypatch):
    conn, token, calls = ready
    _gateway(monkeypatch, calls, fails="")
    assert handoff_coordinator.advance(conn, token)["phase"] == "launched"
    conn.execute("UPDATE brief_handoffs SET deadline = 0 WHERE token = ?", (token,))
    conn.commit()

    report = handoff_coordinator.advance(conn, token)

    assert "resume" not in calls
    assert "may be running" in report["missing"][0]
