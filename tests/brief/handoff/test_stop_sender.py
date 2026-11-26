"""Stopping a sender in its pane, on a private tmux server, where the harness is a child of
the pane's interactive shell that ignores SIGHUP, as a typed `nohup` launch would be."""

import argparse
import contextlib
import dataclasses
import shutil
import tempfile
import time
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import Mock

import pytest

from lemonaid.brief import attached
from lemonaid.brief.handoff import cli as handoff_cli
from lemonaid.brief.handoff import coordinator as handoff_coordinator
from lemonaid.brief.handoff import self_started
from lemonaid.brief.handoff import state as handoff_state
from lemonaid.launch.restart import pane, process
from lemonaid.openclaw import gateway, lemons, sessions, sync

THREAD = "01a2132a-0c1d-7000-8000-000000000003"


@pytest.fixture
def shell_pane(tmp_path):
    """(pane, its shell, the shell's child harness)."""
    if not shutil.which("tmux"):
        pytest.skip("tmux unavailable")
    directory = tempfile.TemporaryDirectory(prefix="stop-sender-", dir="/tmp")
    socket = str(Path(directory.name) / "tmux")
    child = None
    try:
        pane.run(
            socket,
            "-f",
            "/dev/null",
            "new-session",
            "-d",
            "-s",
            "test",
            "-c",
            str(tmp_path),
            "exec /bin/sh -i",
        )
        tty = pane.run(socket, "display-message", "-p", "-t", "test:0", "#{pane_tty}")
        found = pane.locate(socket, tty)
        pane.run(
            socket, "send-keys", "-t", found.pane, "sh -c \"trap '' HUP; exec sleep 300\"", "Enter"
        )
        for _ in range(100):
            child = next((p for p in process.on_tty(tty) if p.pid != found.pid), None)
            if child and Path(child.executable).name == "sleep":
                break
            time.sleep(0.05)
        assert child is not None and Path(child.executable).name == "sleep"
        yield found, process.inspect(found.pid), child
    finally:
        with contextlib.suppress(ValueError):
            pane.run(socket, "kill-server")
        if child is not None and process.same(child):
            process.terminate(child)
        directory.cleanup()


def test_the_senders_harness_is_gone_before_the_placeholder_starts(
    setup, shell_pane, monkeypatch, tmp_path
):
    conn, path = setup
    found, shell, child = shell_pane
    plan = {
        "source": dataclasses.asdict(child),
        "root": dataclasses.asdict(shell),
        "pane": dataclasses.asdict(found),
        "cwd": str(tmp_path),
        "exit_option": pane.exit_option(found),
    }
    monkeypatch.setattr(self_started.planning, "build", lambda *_args, **_kwargs: plan)
    monkeypatch.setattr(self_started.registry, "mine", lambda *_: [])
    row = handoff_state.request(
        conn,
        path,
        "claude:old",
        "openclaw",
        "test",
        "0",
        found.window,
        found.pane,
        "sleep",
        time.time() + 600,
    )

    held = self_started._stop_sender(conn, row)

    assert not process.same(child)
    assert not process.same(shell)
    assert held != str(shell.pid)
    for _ in range(50):
        if "handed its brief to openclaw" in pane.run(
            found.socket, "capture-pane", "-p", "-t", found.pane
        ):
            break
        time.sleep(0.1)
    assert "handed its brief to openclaw" in pane.run(
        found.socket, "capture-pane", "-p", "-t", found.pane
    )


def test_ready_from_the_sender_stops_nothing_and_the_watcher_completes_it(
    setup, shell_pane, monkeypatch, tmp_path
):
    conn, path = setup
    found, shell, child = shell_pane
    plan = {
        "source": dataclasses.asdict(child),
        "root": dataclasses.asdict(shell),
        "pane": dataclasses.asdict(found),
        "cwd": str(tmp_path),
        "exit_option": pane.exit_option(found),
    }
    created: list[str] = []
    monkeypatch.setenv("TMUX", f"{found.socket},0,0")
    monkeypatch.setattr(self_started.planning, "build", lambda *_args, **_kwargs: plan)
    monkeypatch.setattr(self_started.registry, "mine", lambda *_: [])
    monkeypatch.setattr(
        sync, "agents", lambda cli: {"main": sync.Agent("main", "Ada", str(tmp_path), True)}
    )

    def call(cli, method, params, timeout):
        created.append(params.get("key", method))
        return {"sessionId": "s"}

    monkeypatch.setattr(gateway, "call", call)
    monkeypatch.setattr(handoff_cli.db, "connect", lambda: nullcontext(conn))
    monkeypatch.setattr(handoff_cli.request, "watch", Mock())
    row = handoff_state.request(
        conn,
        path,
        "claude:old",
        "openclaw",
        "test",
        "0",
        found.window,
        found.pane,
        "sleep",
        time.time() + 600,
    )
    token = row["token"]
    path.write_text(path.read_text().replace("Old notes.", f"Notes.\nHandoff-Ready: {token}"))

    monkeypatch.setattr(handoff_cli.lemon, "self_channel", lambda conn: "claude:old")
    handoff_cli._cmd(argparse.Namespace(watch=False, to=None, token=token, action="ready"))

    assert process.same(child) and created == []  # the sender's command stopped nothing
    assert handoff_coordinator.advance(conn, token)["phase"] == "launched"  # the watcher
    assert not process.same(child)
    key = created[0]

    found_session = sessions.Session(key, "s", "main", "direct", "", 0, 0, 0)
    lemons.register(conn, found_session, THREAD, None, str(tmp_path), "openclaw-chat", "Next")
    monkeypatch.setenv("CODEX_THREAD_ID", THREAD)
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / ".openclaw/agents/main/agent/codex-home"))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(handoff_cli.lemon, "self_channel", lambda conn: sessions.channel(key))
    handoff_cli._cmd(argparse.Namespace(watch=False, to=None, token=token, action="accept"))

    assert handoff_state.get(conn, token)["phase"] == "complete"
    assert attached.by_channel(conn, [sessions.channel(key)])[sessions.channel(key)] == path
