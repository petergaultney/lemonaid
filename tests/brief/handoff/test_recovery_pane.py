"""Recovery's actual stop/replace operations on a private tmux server."""

import dataclasses
import time
from pathlib import Path

from lemonaid.brief.handoff import coordinator, recovery, request, state
from lemonaid.launch.restart import pane, process


def test_recovery_reuses_existing_pane_without_extra_window(setup, server, monkeypatch):
    conn, path = setup
    deadline = time.monotonic() + 3
    source = process.inspect(server.pid)
    while (
        source is not None
        and Path(source.executable).name != "sleep"
        and time.monotonic() < deadline
    ):
        time.sleep(0.01)
        source = process.inspect(server.pid)
    assert source is not None and Path(source.executable).name == "sleep"
    plan = {
        "source": dataclasses.asdict(source),
        "root": dataclasses.asdict(source),
        "pane": dataclasses.asdict(server),
        "cwd": server.cwd,
        "exit_option": "",
    }
    monkeypatch.setenv("LEMONAID_BRIEFS_DIR", str(path.parent))
    monkeypatch.setenv("TMUX", f"{server.socket},0,0")
    monkeypatch.setattr(recovery.planning, "build", lambda *_args, **_kwargs: plan)
    monkeypatch.setattr(recovery.registry, "mine", lambda *_: [])
    monkeypatch.setattr(recovery.handoff_launch, "configured_line", lambda *_: "codex --no-daemon")
    monkeypatch.setattr(recovery.command, "harness_line", lambda *_: ("exec sleep 30", {}))
    monkeypatch.setattr(
        coordinator, "source", lambda *_: (path, "test", "0", server.window, server.pane, "sleep")
    )
    token, _, _ = request.prepare(conn, "codex", source="claude:old", recover=True)
    windows = pane.run(server.socket, "list-windows", "-F", "#{window_id}")
    recovery.launch(conn, state.get(conn, token))
    row = state.get(conn, token)
    replacement = pane.by_id(server.socket, server.pane)
    assert row["phase"] == "launched"
    assert row["source_pane_id"] == row["target_pane_id"] == replacement.pane
    assert row["source_window_id"] == row["target_window_id"] == replacement.window
    assert replacement.pid != source.pid and not replacement.dead
    assert not process.same(source)
    assert pane.run(server.socket, "list-windows", "-F", "#{window_id}") == windows
