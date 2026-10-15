"""Opt-in authenticated native acceptance in a private home, cwd and tmux server."""

import contextlib
import os
import shlex
import tempfile
import time
from pathlib import Path

import pytest

from lemonaid.brief import attached
from lemonaid.brief import store as briefs
from lemonaid.config import Config
from lemonaid.inbox import db
from lemonaid.launch.restart import coordinator, native, pane, planning, process, settings, state
from lemonaid.watch import registry, stopping

from . import native_codex
from .native_helpers import codex_turn, terminal_flags
from .native_jobs import start_background_job


@pytest.mark.skipif(
    os.environ.get("LEMONAID_TEST_AUTHENTICATED_RESTART") != "1",
    reason="opt-in authenticated native canary",
)
def test_authenticated_codex_same_session_settings_and_tool_turn(tmp_path, monkeypatch):
    binary, home, cwd, flags, prompt, private_auth = native_codex.prepare(tmp_path, monkeypatch)
    with tempfile.TemporaryDirectory(prefix="authenticated-restart-", dir="/tmp") as directory:
        socket = str(Path(directory) / "tmux")
        try:
            pane.run(
                socket,
                "-f",
                "/dev/null",
                "new-session",
                "-d",
                "-s",
                "canary",
                "-c",
                str(cwd),
                "exec sleep 120",
            )
            target = pane.by_id(socket, "%0")
            pane.preserve(target)
            pane.run(
                socket,
                "respawn-pane",
                "-k",
                "-t",
                target.pane,
                "exec " + shlex.join([binary, *flags, prompt]),
            )
            target = pane.by_id(socket, target.pane)

            def completed(previous=0):
                return codex_turn(home, socket, target, previous)

            before = completed()
            tty_flags = terminal_flags(target.tty)
            (tmp_path / "native-screen-before.txt").write_text(
                pane.run(socket, "capture-pane", "-p", "-t", target.pane)
            )
            assert any(
                r.get("payload", {}).get("name") in ("exec", "exec_command", "shell_command")
                for r in before
            )
            session = before[0]["payload"]["id"]
            contexts = [r["payload"] for r in before if r["type"] == "turn_context"]
            source_settings = {
                "model": contexts[-1]["model"],
                "sandbox": "read-only",
                "approval": "on-request",
                "profile": "restart_canary",
                "effort": "high",
                "provider": "openai",
                "argv": [binary, *flags],
                "environment": {"CODEX_HOME": str(home), "PATH": os.environ["PATH"]},
            }
            row = db.Notification(
                1, "codex:" + session, "", metadata={"session_id": session, "cwd": str(cwd)}
            )
            command = settings.command(row, Config(), source_settings)
            candidates = [
                p for p in process.on_tty(target.tty) if Path(p.executable).name == "codex"
            ]
            assert len(candidates) == 1
            source = candidates[0]
            brief = briefs.briefs_dir() / "native-codex.md"
            brief.parent.mkdir(parents=True, exist_ok=True)
            lemon_id = briefs.new_lemon_id(brief)
            brief.write_text(
                f"# Isolated native restart\n\nBrief-ID: {lemon_id}\n\n## Now\n\nReply RESTART_CANARY_AFTER after restart. Do not use tools.\n"
            )
            transcript = next(home.glob("sessions/**/*.jsonl"))
            with db.connect() as conn:
                db.add(
                    conn,
                    row.channel,
                    "native canary",
                    metadata={
                        **row.metadata,
                        "session_path": str(transcript),
                        "tty": target.tty,
                        "tmux_socket": socket,
                    },
                )
                attached.attach(conn, row.channel, brief)
                bound = native.registered(conn, row.channel)
                assert bound is not None and bound["identity"]["pid"] == source.pid
            jobs = start_background_job(socket, target, source, completed, 1, "codex")
            try:
                with db.connect() as conn, pytest.raises(ValueError, match="Unmanaged jobs"):
                    planning.build(conn, row.channel, Config(), force=True)
            finally:
                for job in jobs:
                    process.terminate(job)
                deadline = time.monotonic() + 5
                while process.descendants(source.pid) and time.monotonic() < deadline:
                    time.sleep(0.1)
            with db.connect() as conn:
                plan = planning.build(conn, row.channel, Config(), force=True)
                token = state.reserve(conn, plan)
            coordinator.run(token)
            with db.connect() as conn:
                operation = state.get(conn, token)
                assert operation["phase"] == "complete", operation
                assert not any(process.same(process.Identity(**entry)) for entry in plan["helpers"])
                bound = native.registered(conn, row.channel)
                assert bound["token"] == token
            replacement = pane.by_id(socket, target.pane)
            assert replacement.pane == target.pane and replacement.window == target.window
            target = replacement
            after = completed(2)
            assert terminal_flags(target.tty) == tty_flags
            assert after[0]["payload"]["id"] == session
            (tmp_path / "native-screen-after.txt").write_text(
                pane.run(socket, "capture-pane", "-p", "-t", target.pane)
            )
            resumed = [r["payload"] for r in after if r["type"] == "turn_context"][-1]
            for key in ("model", "effort", "approval_policy", "sandbox_policy"):
                assert resumed.get(key) == contexts[-1].get(key), (
                    key,
                    resumed.get(key),
                    contexts[-1].get(key),
                )
            assert command.count("--no-daemon") == 1
            assert replacement.pane == target.pane
        finally:
            for waiter in registry.mine("codex:" + locals().get("session", "")):
                stopping.stop(waiter, "private native canary cleanup")
            with contextlib.suppress(ValueError):
                pane.run(socket, "kill-server")
            private_auth.unlink(missing_ok=True)
