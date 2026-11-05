"""Move a synthetic Codex out of a shell pane on a private tmux server."""

import contextlib
import dataclasses
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from lemonaid.config import load_config
from lemonaid.inbox import db
from lemonaid.launch.move import coordinator, destination, planning
from lemonaid.launch.restart import pane, process, state
from lemonaid.watch import registry, stopping

from ..restart import runtime_fixture, shared

_until = runtime_fixture._until


def _hook() -> str:
    return shlex.join(
        [
            sys.executable,
            "-c",
            "from unittest.mock import patch; from lemonaid.hooks import session_start\n"
            "with patch.object(session_start.codex_scout, 'ensure_for', return_value=False):\n"
            "    session_start.handle('codex')",
        ]
    )


@pytest.fixture
def shell_pane(tmp_path, monkeypatch):
    """A Codex typed into an interactive shell, as a person or `place open` starts one."""
    if not shutil.which("tmux") or not shutil.which("cc"):
        pytest.skip("tmux and a C compiler are needed")
    monkeypatch.setenv("LEMONAID_DB", str(db.get_db_path()))
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "harness.c").write_text(runtime_fixture._HARNESS)
    subprocess.run(
        ["cc", str(bin_dir / "harness.c"), "-o", str(bin_dir / "codex")],
        check=True,
        capture_output=True,
    )
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ["PATH"])
    (tmp_path / "home" / ".codex").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "home" / ".codex"))
    monkeypatch.setenv("TEST_HOOK", _hook())
    monkeypatch.setenv("TEST_SESSION", shared.SESSION)
    monkeypatch.setenv("TEST_STARTED", str(tmp_path / "started"))
    monkeypatch.setenv("TEST_PROMPT", str(tmp_path / "prompt"))
    config = tmp_path / "config.toml"
    config.write_text(
        '[backends.codex]\nresume_command = "codex --no-daemon resume {session_id}"\n'
    )
    monkeypatch.setenv("LEMONAID_CONFIG", str(config))
    source = tmp_path / "source"
    source.mkdir()
    with db.connect() as conn:
        shared.setup(conn, source)
    server = tempfile.TemporaryDirectory(prefix="move-runtime-", dir="/tmp")
    socket = str(Path(server.name) / "tmux")
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
            str(source),
            "exec /bin/sh",
        )
        pane.run(socket, "send-keys", "-t", "test:0", "codex --no-daemon", "Enter")
        _until(lambda: (tmp_path / "started").exists())
        tty = pane.run(socket, "display-message", "-p", "-t", "test:0", "#{pane_tty}")
        with db.connect() as conn:
            conn.execute(
                "UPDATE notifications SET metadata = json_patch(metadata, ?) WHERE channel = ?",
                (
                    json.dumps({"tmux_socket": socket, "tty": tty, "tmux_session": "test"}),
                    shared.CHANNEL,
                ),
            )
            conn.commit()
        yield socket, tty
    finally:
        for waiter in registry.mine(shared.CHANNEL):
            stopping.stop(waiter, "test cleanup")
        with contextlib.suppress(ValueError):
            pane.run(socket, "kill-server")
        server.cleanup()


def test_moves_into_a_new_session_and_closes_the_old_pane(shell_pane, tmp_path):
    socket, tty = shell_pane
    target = tmp_path / "dest"
    target.mkdir()
    config = load_config()
    with db.connect() as conn:
        row = db.get_by_channel(conn, shared.CHANNEL, unread_only=False)
        to = destination.resolve(str(target), None, row.metadata, "tmux", config, acquire=True)
        plan = planning.build(conn, shared.CHANNEL, to, config, True)
    token = state.reserve(plan)
    coordinator.run(token)

    result = state.get(token)
    assert result["phase"] == "started", result
    assert "closed its old pane" in result["left_behind"]
    sessions = pane.run(socket, "list-sessions", "-F", "#{session_name}").split()
    assert sessions == [to.workspace]  # the old session held only this lemon
    paths = pane.run(
        socket, "list-panes", "-s", "-t", f"={to.workspace}", "-F", "#{pane_current_path}"
    )
    assert str(target.resolve()) in paths.split()
    assert "You were just moved to " + str(target.resolve()) in (tmp_path / "prompt").read_text()
    with db.connect() as conn:
        moved = db.get_by_channel(conn, shared.CHANNEL, unread_only=False).metadata
    assert moved["cwd"] == str(target.resolve())
    assert moved["tmux_session"] == to.workspace
    assert moved["tty"] != tty


def test_a_failed_start_leaves_the_lemon_resumable_in_the_destination(
    shell_pane, tmp_path, monkeypatch
):
    target = tmp_path / "dest"
    target.mkdir()
    config = load_config()
    with db.connect() as conn:
        row = db.get_by_channel(conn, shared.CHANNEL, unread_only=False)
        to = destination.resolve(str(target), None, row.metadata, "tmux", config, acquire=True)
        plan = planning.build(conn, shared.CHANNEL, to, config, True)
    refusing = dataclasses.replace(
        coordinator.pick.named("tmux"), start=lambda *a: "no window", relocation=None
    )
    monkeypatch.setattr(coordinator.pick, "named", lambda name: refusing)
    token = state.reserve(plan)
    coordinator.run(token)

    result = state.get(token)
    assert result["phase"] == "failed"
    assert "lemon resume" in result["error"]
    with db.connect() as conn:
        assert db.get_by_channel(conn, shared.CHANNEL, unread_only=False).metadata["cwd"] == str(
            target.resolve()
        )


def test_a_protected_source_session_stays_open(shell_pane, tmp_path):
    socket, _ = shell_pane
    config_file = tmp_path / "config.toml"
    config_file.write_text(config_file.read_text() + '[places]\nprotected_sessions = ["test"]\n')
    target = tmp_path / "dest"
    target.mkdir()
    config = load_config()
    with db.connect() as conn:
        row = db.get_by_channel(conn, shared.CHANNEL, unread_only=False)
        to = destination.resolve(str(target), None, row.metadata, "tmux", config, acquire=True)
        plan = planning.build(conn, shared.CHANNEL, to, config, True)
    token = state.reserve(plan)
    coordinator.run(token)

    result = state.get(token)
    assert result["phase"] == "started", result
    assert "is protected" in result["left_behind"]
    assert "test" in pane.run(socket, "list-sessions", "-F", "#{session_name}").split()


def test_claude_trust_is_recorded_before_the_lemon_stops(shell_pane, tmp_path, monkeypatch):
    target = tmp_path / "dest"
    target.mkdir()
    config = load_config()
    with db.connect() as conn:
        row = db.get_by_channel(conn, shared.CHANNEL, unread_only=False)
        to = destination.resolve(str(target), None, row.metadata, "tmux", config, acquire=True)
        plan = planning.build(conn, shared.CHANNEL, to, config, True)
    monkeypatch.setattr(coordinator.trust, "config_file", lambda: tmp_path / "missing.json")
    token = state.reserve({**plan, "claude_trust": True})
    coordinator.run(token)

    assert state.get(token)["phase"] == "failed"
    assert process.same(process.Identity(**plan["source"]))
