"""Opt-in native command acceptance, using only temporary homes and test-owned sessions."""

import contextlib
import json
import os
import shlex
import tempfile
import time
from pathlib import Path

import pytest

from lemonaid.brief import attached
from lemonaid.brief import store as briefs
from lemonaid.config import load_config
from lemonaid.inbox import db
from lemonaid.launch.restart import coordinator, native, pane, planning, process, state
from lemonaid.watch import registry, stopping

from . import native_claude, native_codex
from .native_helpers import claude_turn, codex_turn


@pytest.mark.skipif(
    os.environ.get("LEMONAID_TEST_AUTHENTICATED_RESTART") != "1",
    reason="opt-in private authenticated native canary",
)
@pytest.mark.parametrize("harness", ["claude", "codex"])
def test_native_configured_resume_accepts_same_session_and_restart_prompt(
    tmp_path, monkeypatch, harness
):
    if harness == "claude":
        binary, home, cwd, sid, flags, private_auth = native_claude.prepare(
            tmp_path, monkeypatch, True
        )
        source_argv = [
            binary,
            *flags,
            "--session-id",
            sid,
            "Reply exactly RESTART_CANARY_BEFORE. Do not use tools.",
        ]
        resume_command = f"{shlex.quote(binary)} --resume {{session_id}}"
    else:
        binary, home, cwd, flags, prompt, private_auth = native_codex.prepare(tmp_path, monkeypatch)
        source_argv = [binary, *flags, prompt]
        resume_command = (
            f"{shlex.quote(binary)} --dangerously-bypass-hook-trust resume {{session_id}}"
        )
    Path(os.environ["LEMONAID_CONFIG"]).write_text(
        f"[backends.{harness}]\nresume_command = {json.dumps(resume_command)}\n"
    )
    with tempfile.TemporaryDirectory(prefix="small-restart-native-", dir="/tmp") as directory:
        socket = str(Path(directory) / "tmux")
        channel = ""
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
                "exec " + shlex.join(source_argv),
            )
            target = pane.by_id(socket, "%0")
            if harness == "claude":
                claude_turn(home, sid, socket, target, "RESTART_CANARY_BEFORE")
                transcript = next(home.glob(f"projects/*/{sid}.jsonl"))
                channel = "claude:" + sid[:8]
            else:
                records = codex_turn(home, socket, target)
                sid = records[0]["payload"]["id"]
                transcript = next(home.glob("sessions/**/*.jsonl"))
                channel = "codex:" + sid
            brief = briefs.briefs_dir() / "native-small.md"
            brief.parent.mkdir(parents=True, exist_ok=True)
            lemon_id = briefs.new_lemon_id(brief)
            brief.write_text(
                f"# Isolated restart\n\nBrief-ID: {lemon_id}\n\n## Now\n\nAfter restart, continue this isolated test. Do not read or modify unrelated files.\n"
            )
            with db.connect() as conn:
                db.add(
                    conn,
                    channel,
                    "native test",
                    switch_source="tmux",
                    metadata={
                        "cwd": str(cwd),
                        "session_id": sid,
                        "tty": target.tty,
                        "tmux_socket": socket,
                    },
                )
                attached.attach(conn, channel, brief)
                plan = planning.build(conn, channel, load_config(), True)
            source = process.Identity(**plan["source"])
            original_binding = native.binding(channel)
            token = state.reserve(plan)
            coordinator.run(token)
            assert state.get(token)["phase"] == "started", state.get(token)
            replacement = pane.by_id(socket, target.pane)
            assert replacement.pane == target.pane and replacement.window == target.window
            assert not process.same(source)
            deadline = time.monotonic() + 30
            # Acceptance means the native CLI resumes the saved transcript and accepts the prompt.
            # The coordinator itself does not wait for the model or require it to rearm a watcher.
            while time.monotonic() < deadline:
                text = transcript.read_text()
                bound = native.binding(channel)
                if planning.PROMPT in text and bound != original_binding:
                    break
                time.sleep(0.2)
            assert planning.PROMPT in transcript.read_text(), pane.run(
                socket, "capture-pane", "-p", "-t", target.pane
            )
            assert native.binding(channel)["session_id"] == sid
            assert native.binding(channel)["identity"] != original_binding["identity"]
        finally:
            for waiter in registry.mine(channel):
                stopping.stop(waiter, "private native canary cleanup")
            with contextlib.suppress(ValueError):
                pane.run(socket, "kill-server")
            private_auth.unlink(missing_ok=True)
            if harness == "claude":
                (home / ".claude.json").unlink(missing_ok=True)
