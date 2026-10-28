"""Shared isolated inbox and brief for handoff tests."""

import time
from dataclasses import asdict
from unittest.mock import Mock

import pytest

from lemonaid.brief import attached, store
from lemonaid.brief.handoff import recovery
from lemonaid.brief.handoff import state as handoff_state
from lemonaid.inbox import db, pins


@pytest.fixture
def setup(tmp_path):
    path = tmp_path / "handoff.md"
    lemon_id = store.new_lemon_id(path)
    path.write_text(
        f"# Handoff\n\nStatus: working\n\nLemon-ID: {lemon_id}\n\n"
        "## Now\n\n### Next\n\n- Continue.\n\n## Handoff\n\nOld notes.\n"
    )
    with db.connect(tmp_path / "inbox.db") as conn:
        conn.execute("INSERT INTO lemon_identities VALUES (?, ?)", (str(path), lemon_id))
        conn.execute("INSERT INTO lemon_aliases VALUES (?, ?)", ("old-id.Alias", lemon_id))
        conn.execute(
            "INSERT INTO lemon_parents VALUES (?, ?, ?)", (lemon_id, "parent.Other", time.time())
        )
        db.add(
            conn,
            channel="claude:old",
            message="Old text",
            name="Old backend",
            metadata={"session_id": "old", "cwd": str(tmp_path)},
            status="read",
        )
        db.add(
            conn,
            channel="codex:new",
            message="New text",
            name="New backend",
            metadata={"session_id": "new", "cwd": str(tmp_path)},
            status="read",
        )
        attached.attach(conn, "claude:old", path)
        db.update_name(
            conn, db.get_by_channel(conn, "claude:old", unread_only=False).id, "Manual name"
        )
        pins.pin(conn, "claude:old")
        conn.execute(
            "INSERT INTO session_emoji VALUES (?, ?, ?)", ("claude:old", "🍋", time.time())
        )
        conn.commit()
        yield conn, path


def requested(conn, path):
    row = handoff_state.request(
        conn, path, "claude:old", "codex", "work", "2", "@2", "%2", "claude", time.time() + 600
    )
    path.write_text(
        path.read_text().replace("Old notes.", f"New notes.\nHandoff-Ready: {row['token']}")
    )
    return row


def recovery_runtime(monkeypatch, path):
    source = recovery.process.Identity(11, 10, "test", "source-start", "/bin/claude")
    root = recovery.process.Identity(10, 1, "test", "shell-start", "/bin/zsh")
    target = recovery.pane.Pane(
        "/tmp/test.sock", "%2", "@2", "/dev/test", 10, False, str(path.parent)
    )
    replacement = recovery.pane.Pane(target.socket, "%2", "@2", target.tty, 99, False, target.cwd)
    plan = {
        "source": asdict(source),
        "root": asdict(root),
        "pane": asdict(target),
        "cwd": target.cwd,
        "exit_option": "",
        "channel": "claude:old",
    }
    events = []
    alive = {"source": True, "replaced": False}

    def terminate(identity):
        assert identity == source
        events.append("stop")
        alive["source"] = False

    def replace(*args):
        assert args[0] == target and args[1] == root
        events.append("replace")
        alive["replaced"] = True
        return replacement

    monkeypatch.setattr(recovery.planning, "build", Mock(return_value=plan))
    monkeypatch.setattr(recovery.process, "ancestry", lambda *_: [])
    monkeypatch.setattr(recovery.process, "terminate", Mock(side_effect=terminate))
    monkeypatch.setattr(
        recovery.process, "same", lambda identity: alive["source"] if identity == source else True
    )
    monkeypatch.setattr(recovery.pane, "preserve", Mock())
    monkeypatch.setattr(recovery.pane, "replace", Mock(side_effect=replace))
    monkeypatch.setattr(recovery.pane, "restore", Mock())
    monkeypatch.setattr(recovery.registry, "mine", lambda *_: [])
    monkeypatch.setattr(
        recovery.handoff_tmux,
        "pane_process",
        lambda *_: ("99" if alive["replaced"] else "10", False),
    )
    monkeypatch.setattr(recovery.handoff_tmux, "remain_on_exit", lambda *_: "off")
    monkeypatch.setattr(recovery.handoff_tmux, "set_remain_on_exit", Mock(return_value=True))
    return {"plan": plan, "events": events, "alive": alive, "source": source, "target": target}
