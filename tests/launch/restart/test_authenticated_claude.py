"""Installed Claude acceptance without modifying a live session or native home."""

import contextlib
import os
import shlex
import tempfile
import time
from pathlib import Path

import pytest

from lemonaid.brief import attached
from lemonaid.brief import store as briefs
from lemonaid.claude import session_socket
from lemonaid.config import Config
from lemonaid.inbox import db
from lemonaid.launch.restart import (
    coordinator,
    native,
    pane,
    planning,
    process,
    settings,
    state,
    watchers,
)
from lemonaid.messages import store
from lemonaid.watch import registry, stopping

from . import native_claude
from .native_helpers import claude_turn, terminal_flags
from .native_jobs import start_background_job


@pytest.mark.skipif(
    os.environ.get("LEMONAID_TEST_AUTHENTICATED_RESTART") != "1",
    reason="opt-in authenticated native canary",
)
@pytest.mark.parametrize("session_hook", [False, True])
def test_authenticated_claude_resume_and_new_socket_delivery(tmp_path, monkeypatch, session_hook):
    binary, home, cwd, sid, flags, private_auth = native_claude.prepare(
        tmp_path, monkeypatch, session_hook
    )
    with tempfile.TemporaryDirectory(prefix="authenticated-claude-", dir="/tmp") as directory:
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
            prompt = "Use the Bash tool to run pwd, then reply exactly RESTART_CANARY_BEFORE. Do not read or change any other files."
            pane.run(
                socket,
                "respawn-pane",
                "-k",
                "-t",
                target.pane,
                "exec " + shlex.join([binary, *flags, "--session-id", sid, prompt]),
            )
            target = pane.by_id(socket, target.pane)

            def completed(marker, previous=0):
                return claude_turn(home, sid, socket, target, marker, previous)

            before = completed("RESTART_CANARY_BEFORE")
            tty_flags = terminal_flags(target.tty)
            messages = [
                r["message"]
                for r in before
                if r.get("type") == "assistant"
                and r.get("message", {}).get("model") != "<synthetic>"
            ]
            assert any(
                c.get("type") == "tool_use" and c.get("name") == "Bash"
                for m in messages
                for c in m.get("content", [])
            )
            model = messages[-1]["model"]
            deadline = time.monotonic() + 10
            entry = session_socket.find(sid, home)
            while entry is None and time.monotonic() < deadline:
                time.sleep(0.2)
                entry = session_socket.find(sid, home)
            assert entry is not None
            with db.connect() as conn:
                bound = native.registered(conn, "claude:" + sid[:8])
            assert bound is not None and bound["identity"]["pid"] == entry.pid
            assert bound["settings"]["permission"] == "default"
            old_socket = entry.socket
            row = db.Notification(
                1, "claude:" + sid[:8], "", metadata={"session_id": sid, "cwd": str(cwd)}
            )
            effective = bound["settings"]
            assert settings.command(row, Config(), effective)[0] == binary
            brief = briefs.briefs_dir() / "native-claude.md"
            brief.parent.mkdir(parents=True, exist_ok=True)
            lemon_id = briefs.new_lemon_id(brief)
            brief.write_text(
                f"# Isolated restart canary\n\nBrief-ID: {lemon_id}\n\n## Now\n\nReply exactly RESTART_CANARY_AFTER after restart. Do not use tools except reading this brief.\n"
            )
            with db.connect() as conn:
                db.add(
                    conn,
                    row.channel,
                    "canary",
                    metadata={
                        **row.metadata,
                        "tty": target.tty,
                        "tmux_socket": socket,
                        "transcript_path": str(next(home.glob(f"projects/*/{sid}.jsonl"))),
                    },
                )
                attached.attach(conn, row.channel, brief)
            watcher_plan = {
                "channel": row.channel,
                "harness": "claude",
                "session_id": sid,
                "cwd": str(cwd),
                "settings": effective,
            }
            watchers.restore(watcher_plan)
            deadline = time.monotonic() + 5
            while (
                model not in pane.run(socket, "capture-pane", "-p", "-t", target.pane)
                and time.monotonic() < deadline
            ):
                time.sleep(0.1)
            source = process.inspect(entry.pid)
            jobs = start_background_job(
                socket, target, source, lambda _: completed("BACKGROUND_READY"), 1, "claude"
            )
            try:
                with db.connect() as conn, pytest.raises(ValueError, match="Unmanaged jobs"):
                    planning.build(conn, row.channel, Config(), force=True)
            finally:
                for job in jobs:
                    process.terminate(job)
                time.sleep(0.5)
            with db.connect() as conn:
                plan = planning.build(conn, row.channel, Config(), force=True)
                token = state.reserve(conn, plan)
            coordinator.run(token)
            with db.connect() as conn:
                operation = state.get(conn, token)
                assert operation["phase"] == "complete", operation
                assert not any(process.same(process.Identity(**entry)) for entry in plan["helpers"])
            target = pane.by_id(socket, target.pane)
            after = completed("", previous=2)
            assert terminal_flags(target.tty) == tty_flags
            assert [
                r["message"]["model"]
                for r in after
                if r.get("type") == "assistant"
                and r.get("message", {}).get("model") != "<synthetic>"
            ][-1] == model
            fresh = session_socket.find(sid, home)
            assert fresh is not None and fresh.pid != entry.pid and fresh.socket != old_socket
            with db.connect() as conn:
                bound = native.registered(conn, row.channel)
            assert bound["token"] == token
            assert bound["identity"]["pid"] == fresh.pid
            assert bound["settings"]["model"] == model
            assert bound["settings"]["permission"] == "default"
            watchers.restore(watcher_plan)
            pending = store.send(
                store.inbox_for_id(lemon_id),
                "Reply exactly RESTART_CANARY_DELIVERED. Do not use tools. This is an isolated native delivery test.",
                "test",
            )
            completed("RESTART_CANARY_DELIVERED")
            assert not pending.exists()
            if session_hook:
                native_claude.select_model(
                    socket, target, row.channel, model, process.Identity(**bound["identity"])
                )
        finally:
            for waiter in registry.mine("claude:" + sid[:8]):
                stopping.stop(waiter, "private native canary cleanup")
            with contextlib.suppress(ValueError):
                pane.run(socket, "kill-server")
            private_auth.unlink(missing_ok=True)
            (home / ".claude.json").unlink(missing_ok=True)
