"""Composer submit sequences sent through tmux."""

import shutil
import subprocess
import time
import uuid

import pytest

from lemonaid.tmux import submit


def test_submit_uses_literal_csi_u_for_control_enter(monkeypatch):
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(submit.subprocess, "run", run)

    submit.send("%2", "C-Enter")
    submit.send("%2", "Enter")

    assert calls == [
        (
            ["tmux", "send-keys", "-t", "%2", "-H", "1b", "5b", "31", "33", "3b", "35", "75"],
            {"capture_output": True},
        ),
        (["tmux", "send-keys", "-t", "%2", "Enter"], {"capture_output": True}),
    ]


def test_control_enter_reaches_a_pane_as_csi_u(monkeypatch, tmp_path):
    if not shutil.which("tmux"):
        pytest.skip("tmux not installed")

    name = f"lemonaid-submit-{uuid.uuid4().hex[:8]}"
    output = tmp_path / "keys"
    command = f"stty raw -echo; cat > {output}"
    started = subprocess.run(
        ["tmux", "-L", name, "-f", "/dev/null", "new-session", "-d", "-s", "probe", command],
        capture_output=True,
    )
    if started.returncode != 0:
        pytest.skip(f"cannot start tmux: {started.stderr.decode().strip()}")

    def tmux(*args):
        return subprocess.run(
            ["tmux", "-L", name, *args], capture_output=True, text=True
        ).stdout.strip()

    socket_path = tmux("display", "-p", "#{socket_path}")
    if not socket_path:
        tmux("kill-server")
        pytest.skip("cannot query isolated tmux server")

    monkeypatch.setenv("TMUX", f"{socket_path},0,0")
    try:
        assert submit.send("probe", "C-Enter").returncode == 0
        for _ in range(40):
            if output.exists() and output.read_bytes() == b"\x1b[13;5u":
                break
            time.sleep(0.05)
        assert output.read_bytes() == b"\x1b[13;5u"
    finally:
        tmux("kill-server")
