"""Windows restore reserves ahead of their lemons, on a real private server."""

import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import pytest

from lemonaid.restore import run
from lemonaid.tmux import placement
from lemonaid.tmux import restore as tmux_restore


@pytest.fixture
def server(monkeypatch):
    if not shutil.which("tmux"):
        pytest.skip("tmux is not installed")
    socket = str(Path(tempfile.mkdtemp(prefix="lma-reserve-", dir="/tmp")) / "s")
    monkeypatch.setenv("SHELL", "/bin/sh")  # the shell a taken window starts
    subprocess.run(
        ["tmux", "-S", socket, "-f", "/dev/null", "new-session", "-d", "-s", "here"], check=True
    )
    monkeypatch.setenv("TMUX", f"{socket},0,0")
    yield socket
    subprocess.run(["tmux", "-S", socket, "kill-server"], check=False)


def _tmux(socket: str, *args: str) -> str:
    return subprocess.run(
        ["tmux", "-S", socket, *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def _spot(session: str, index: int) -> run.Spot:
    return run.Spot(f"{session}:{index}", "", placement.Spot(session, index, False, index))


def _windows(socket: str) -> dict[str, str]:
    """Each window as session:index, with what its pane started with."""
    return dict(
        line.split("|", 1)
        for line in _tmux(
            socket,
            "list-windows",
            "-a",
            "-F",
            "#{session_name}:#{window_index}|#{pane_start_command}",
        ).splitlines()
    )


def _made(socket: str) -> list[str]:
    """The sessions in the order tmux made them, which its session ids count."""
    found = [
        line.split(" ", 1)
        for line in _tmux(
            socket, "list-sessions", "-F", "#{session_id} #{session_name}"
        ).splitlines()
    ]
    return [name for _, name in sorted(found, key=lambda each: int(each[0].lstrip("$")))]


def _until(check, timeout: float = 5) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            return True
        time.sleep(0.05)
    return False


def test_sessions_come_back_in_the_order_given_whatever_order_their_lemons_start(server):
    terminal = tmux_restore.terminal(True)
    older, newer = _spot("older", 2), _spot("newer", 1)

    terminal.reserve([(older, "/tmp", "old work"), (newer, "/tmp", "new work")])
    window, why = terminal.open(newer, "/tmp", {"RESTORED": "yes"})

    assert why == ""
    assert _made(server) == ["here", "older", "newer"]
    assert _tmux(server, "display-message", "-p", "-t", window, "#{window_index}") == "1"
    assert _until(  # Linux reads it from the pane's process, which takes a moment to start
        lambda: (
            _tmux(server, "display-message", "-p", "-t", window, "#{pane_current_path}")
            in ("/tmp", "/private/tmp")
        )
    )
    assert "lemonaid-restore" not in _windows(server)["newer:1"]
    assert "lemonaid-restore" in _windows(server)["older:2"]
    assert _until(
        lambda: (
            "lemonaid restore will start old work here."
            in _tmux(server, "capture-pane", "-p", "-t", "older:2")
        )
    )


def test_a_lemon_that_does_not_start_gives_up_its_window(server):
    terminal = tmux_restore.terminal(True)
    spot = _spot("here", 3)
    terminal.reserve([(spot, "/tmp", "gone")])
    assert "here:3" in _windows(server)

    terminal.release(spot)

    assert "here:3" not in _windows(server)


def _panes(socket: str, window: str) -> list[str]:
    return _tmux(socket, "list-panes", "-t", window, "-F", "#{pane_start_command}").splitlines()


@pytest.mark.parametrize("starting", ["open", "release"])
@pytest.mark.parametrize("took", ["respawned", "split"])
def test_a_reserved_window_someone_started_something_in_is_left_alone(server, took, starting):
    terminal = tmux_restore.terminal(True)
    spot = _spot("here", 3)
    terminal.reserve([(spot, "/tmp", "taken")])
    if took == "respawned":
        _tmux(server, "respawn-pane", "-k", "-t", "here:3", "sleep 600")
    else:
        _tmux(server, "split-window", "-d", "-t", "here:3", "sleep 600")
    before = _panes(server, "here:3")

    if starting == "open":
        window, why = terminal.open(spot, "/tmp", {})
        assert (window, bool(why)) == ("", True)
    else:
        terminal.release(spot)

    assert _panes(server, "here:3") == before
    assert any("sleep 600" in pane for pane in before)


def test_windows_keep_their_indices_with_renumbering_on(server):
    """Restore turns `renumber-windows` off only around its own closes and moves."""
    _tmux(server, "set-option", "-g", "base-index", "0")
    _tmux(server, "set-option", "-g", "renumber-windows", "on")
    terminal = tmux_restore.terminal(True)
    two, four, six = _spot("gappy", 2), _spot("gappy", 4), _spot("gappy", 6)
    terminal.reserve([(two, "/tmp", "two"), (four, "/tmp", "four"), (six, "/tmp", "six")])

    window, why = terminal.open(four, "/tmp", {})
    terminal.release(two)

    assert why == ""
    assert _tmux(server, "display-message", "-p", "-t", window, "#{window_index}") == "4"
    assert sorted(i for i in _windows(server) if i.startswith("gappy:")) == ["gappy:4", "gappy:6"]
    assert "lemonaid-restore" in _windows(server)["gappy:6"]
    assert _tmux(server, "show-options", "-t", "gappy", "-qv", "renumber-windows") == ""
    assert _tmux(server, "display-message", "-p", "-t", "gappy", "#{renumber-windows}") in (
        "1",
        "on",
    )


def test_a_started_lemon_gets_the_login_shell_a_new_window_would(server):
    terminal = tmux_restore.terminal(True)
    spot = _spot("here", 3)
    terminal.reserve([(spot, "/tmp", "shell")])

    window, _ = terminal.open(spot, "/tmp", {})

    assert _panes(server, window) == ["/bin/sh -l"]  # run as is, not under another shell
