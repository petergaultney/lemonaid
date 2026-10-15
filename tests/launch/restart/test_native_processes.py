"""Opt-in SIGTERM probes for installed interactive harnesses, with private native homes."""

import contextlib
import os
import shlex
import shutil
import tempfile
import time
from pathlib import Path

import pytest

from lemonaid.launch.restart import pane, process


@pytest.mark.skipif(
    os.environ.get("LEMONAID_TEST_NATIVE_RESTART") != "1",
    reason="opt-in installed native harness probes",
)
@pytest.mark.parametrize("harness", ["claude", "codex"])
@pytest.mark.parametrize("shell_parent", [False, True])
def test_native_sigterm_in_private_terminal(tmp_path, monkeypatch, harness, shell_parent):
    binary = shutil.which(harness)
    if not binary or not shutil.which("tmux"):
        pytest.skip(f"{harness} or tmux unavailable")
    native_home = tmp_path / "native-home"
    native_home.mkdir()
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(native_home / "claude"))
    monkeypatch.setenv("CODEX_HOME", str(native_home / "codex"))
    (native_home / "codex").mkdir()
    (native_home / "claude").mkdir()
    flags = (
        ["--model", "sonnet", "--permission-mode", "default"]
        if harness == "claude"
        else [
            "--no-daemon",
            "--model",
            "gpt-6.1-sol",
            "--sandbox",
            "read-only",
            "--ask-for-approval",
            "on-request",
            "-c",
            "check_for_update_on_startup=false",
        ]
    )
    directory = tempfile.TemporaryDirectory(prefix="native-restart-", dir="/tmp")
    socket = str(Path(directory.name) / "tmux")
    try:
        line = shlex.join([binary, *flags])
        line = (
            "exec sh -c " + shlex.quote(line + "; exec sleep 30")
            if shell_parent
            else "exec " + line
        )
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
            "exec sleep 30",
        )
        tty = pane.run(socket, "display-message", "-p", "-t", "test:0", "#{pane_tty}")
        target = pane.locate(socket, tty)
        pane.preserve(target)
        pane.run(socket, "respawn-pane", "-k", "-t", target.pane, line)
        time.sleep(0.1)
        target = pane.by_id(socket, target.pane)
        tty = target.tty
        source = None
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            matches = [
                entry
                for entry in process.on_tty(tty)
                if Path(entry.executable).name == harness
                or (harness == "claude" and Path(entry.executable).name.replace(".", "").isdigit())
            ]
            if len(matches) == 1:
                source = matches[0]
                break
            time.sleep(0.1)
        assert source is not None, (
            process.on_tty(tty),
            pane.run(socket, "capture-pane", "-p", "-t", target.pane),
        )
        pane.preserve(target)
        time.sleep(2)
        assert process.same(source)
        screen = pane.run(socket, "capture-pane", "-p", "-t", target.pane)
        assert screen.strip()
        process.terminate(source)
        assert not process.same(source)
        deadline = time.monotonic() + 3
        remaining = process.on_tty(tty)
        while any(entry.pid != target.pid for entry in remaining) and time.monotonic() < deadline:
            time.sleep(0.05)
            remaining = process.on_tty(tty)
        assert all(entry.pid == target.pid for entry in remaining), remaining
        # The parent shell is deliberately retained, and never mistaken for the harness.
        if shell_parent:
            assert pane.check(target).pid == target.pid
        (tmp_path / f"{harness}-probe.txt").write_text(screen)
    finally:
        with contextlib.suppress(ValueError):
            pane.run(socket, "kill-server")
        directory.cleanup()


@pytest.mark.skipif(
    os.environ.get("LEMONAID_TEST_NATIVE_RESTART") != "1",
    reason="opt-in installed native parser probe",
)
def test_generated_codex_command_passes_installed_argument_parser(tmp_path, monkeypatch):
    import subprocess

    from lemonaid.config import Config
    from lemonaid.inbox import db
    from lemonaid.launch.restart import environment, settings

    from . import shared

    if not shutil.which("codex"):
        pytest.skip("codex unavailable")
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "private-codex"))
    row = db.Notification(
        1, shared.CHANNEL, "", metadata={"cwd": str(tmp_path), "session_id": shared.SESSION}
    )
    source = {
        **shared.SETTINGS,
        "environment": environment.capture("codex", os.environ),
        "native_homes": environment.homes(os.environ),
    }
    command = settings.command(row, Config(), source)
    result = subprocess.run(
        command, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=15, cwd=tmp_path
    )
    assert result.returncode != 2, result.stderr
    assert "cannot be used multiple times" not in result.stderr
    assert "unexpected argument" not in result.stderr
    assert command.count("--no-daemon") == 1
