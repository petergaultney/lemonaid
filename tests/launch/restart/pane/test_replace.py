import contextlib
import dataclasses
import shutil
import time
from pathlib import Path

import pytest

from lemonaid.launch.restart import pane, process


@pytest.mark.parametrize("shell", ["bash", "zsh", "fish"])
def test_captured_login_shell_can_be_replaced(server, shell):
    binary = shutil.which(shell)
    if not binary:
        pytest.skip(f"{shell} unavailable")
    pane.run(server.socket, "set-option", "-g", "default-shell", binary)
    pane_id = pane.run(server.socket, "new-window", "-d", "-P", "-F", "#{pane_id}")
    target = pane.by_id(server.socket, pane_id)
    root = process.inspect(target.pid)
    assert root is not None
    assert process.shell(root, [])
    replacement = pane.replace(target, root, target.cwd, "exec sleep 30", {})
    assert replacement.pane == target.pane
    assert replacement.pid != root.pid


def test_login_shell_does_not_admit_other_terminal_jobs(server, monkeypatch):
    root = dataclasses.replace(process.inspect(server.pid), executable="-fish")
    job = dataclasses.replace(root, pid=root.pid + 1, executable="sleep")
    monkeypatch.setattr(process, "on_tty", lambda tty: [root, job])
    monkeypatch.setattr(pane.time, "monotonic", iter([0, 4]).__next__)
    with pytest.raises(ValueError, match="Unmanaged jobs"):
        pane.replace(server, root, server.cwd, "exec false", {})


def test_dead_pane_resumes_without_k_and_preserves_window(server, monkeypatch):
    pane.preserve(server)
    source = process.inspect(server.pid)
    assert source is not None
    process.terminate(source)
    deadline = time.monotonic() + 3
    while not pane.check(server).dead and time.monotonic() < deadline:
        time.sleep(0.05)
    commands = []
    original = pane.run

    def record(socket, *args):
        commands.append(args)
        return original(socket, *args)

    monkeypatch.setattr(pane, "run", record)
    replacement = pane.replace(
        server, source, server.cwd, "exec sleep 30", {"LEMONAID_RESTART_TOKEN": "new"}
    )
    respawn = next(args for args in commands if args[0] == "respawn-pane")
    assert "-k" not in respawn
    assert replacement.pane == server.pane
    assert replacement.window == server.window
    assert replacement.socket == server.socket
    assert replacement.pid != server.pid


def test_changed_pane_is_never_replaced(server):
    wrong = dataclasses.replace(server, pid=server.pid + 1)
    with pytest.raises(ValueError, match="changed"):
        pane.replace(wrong, process.inspect(server.pid), server.cwd, "exec false", {})
    assert process.inspect(server.pid) is not None


def test_same_pane_id_on_other_socket_is_untouched(server):
    other_socket = str(Path(server.socket).parent / "other")
    try:
        pane.run(
            other_socket, "-f", "/dev/null", "new-session", "-d", "-s", "other", "exec sleep 30"
        )
        other = pane.by_id(other_socket, server.pane)
        assert other.pane == server.pane
        pane.preserve(server)
        assert pane.exit_option(other) == ""
        assert process.same(process.inspect(other.pid))
    finally:
        with contextlib.suppress(ValueError):
            pane.run(other_socket, "kill-server")


def test_respawn_keeps_sidebar_layout_and_focus(server):
    pane.run(server.socket, "split-window", "-d", "-t", server.pane, "exec sleep 30")
    pane.run(server.socket, "new-window", "-n", "viewer", "exec sleep 30")
    layout = pane.run(server.socket, "display-message", "-p", "-t", server.pane, "#{window_layout}")
    selected = pane.run(server.socket, "display-message", "-p", "#{window_id}")
    pane.preserve(server)
    source = process.inspect(server.pid)
    process.terminate(source)
    deadline = time.monotonic() + 3
    while not pane.check(server).dead and time.monotonic() < deadline:
        time.sleep(0.05)
    replacement = pane.replace(server, source, server.cwd, "exec sleep 30", {})
    assert replacement.window == server.window
    assert (
        pane.run(server.socket, "display-message", "-p", "-t", server.pane, "#{window_layout}")
        == layout
    )
    assert pane.run(server.socket, "display-message", "-p", "#{window_id}") == selected
