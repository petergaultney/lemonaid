"""A crashed lemon goes back into its own pane, idle at a shell, on a real private server."""

import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import pytest

from lemonaid.inbox import db
from lemonaid.tmux import own_pane
from lemonaid.tmux import restore as tmux_restore


@pytest.fixture
def server(monkeypatch):
    if not shutil.which("tmux"):
        pytest.skip("tmux is not installed")
    socket = str(Path(tempfile.mkdtemp(prefix="lma-own-", dir="/tmp")) / "s")
    subprocess.run(
        [
            "tmux",
            "-S",
            socket,
            "-f",
            "/dev/null",
            "new-session",
            "-d",
            "-s",
            "work",
            "/bin/sh",
            "-i",
        ],
        check=True,
    )
    monkeypatch.setenv("TMUX", f"{socket},0,0")
    yield socket
    subprocess.run(["tmux", "-S", socket, "kill-server"], check=False)


def _tmux(socket: str, *args: str) -> str:
    return subprocess.run(
        ["tmux", "-S", socket, *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def _row(channel: str, socket: str, pane: str) -> db.Notification:
    started = int(_tmux(socket, "display-message", "-p", "#{start_time}"))
    with db.connect() as conn:
        db.add(
            conn,
            channel,
            "waiting",
            metadata={
                "cwd": "/tmp",
                "tmux_socket": socket,
                "tmux_session": "work",
                "tmux_window": "0",
                "tmux_pane_identity": [pane, started],
            },
            upsert=False,
            switch_source="tmux",
        )
        row = db.get_by_channel(conn, channel, unread_only=False)
    assert row is not None
    return row


def _until(check, timeout: float = 5) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            return True
        time.sleep(0.05)
    return False


def test_an_idle_pane_is_reused_in_the_lemons_directory(server, tmp_path):
    pane = _tmux(server, "display-message", "-p", "#{pane_id}")
    row = _row("claude:a", server, pane)

    placed, unplaced = tmux_restore.place([row])

    assert unplaced == []
    [(_, spot)] = placed
    assert (spot.where, spot.at.pane_id) == ("work:0", pane)
    assert tmux_restore.open_window(spot, str(tmp_path), {"MARK": "yes"}) == (pane, "")
    assert _until(
        lambda: (
            _tmux(server, "display-message", "-p", "-t", pane, "#{pane_current_path}")
            == str(tmp_path.resolve())
        )
    )
    tmux_restore.close_window(pane)
    assert _tmux(server, "display-message", "-p", "-t", pane, "#{pane_id}") == pane


def test_a_busy_pane_is_not_reused(server):
    pane = _tmux(server, "display-message", "-p", "#{pane_id}")
    _tmux(server, "send-keys", "-t", pane, "sleep 30", "Enter")
    assert _until(
        lambda: (
            _tmux(server, "display-message", "-p", "-t", pane, "#{pane_current_command}") == "sleep"
        )
    )

    assert own_pane.idle([_row("claude:a", server, pane)]) == {}


def test_a_lemon_recorded_on_another_server_is_not_placed(server):
    row = _row("claude:a", server, "%0")
    with db.connect() as conn:
        db.repair_location(conn, row, {"tmux_socket": "/tmp/elsewhere/default"})
        moved = db.get_by_channel(conn, "claude:a", unread_only=False)
    assert moved is not None

    assert tmux_restore.place([moved]) == (
        [],
        [(moved, "it ran on another tmux server (/tmp/elsewhere/default)")],
    )


def test_a_pane_busy_again_after_planning_is_left_alone(server, tmp_path):
    pane = _tmux(server, "display-message", "-p", "#{pane_id}")
    [(_, spot)], _ = tmux_restore.place([_row("claude:a", server, pane)])
    _tmux(server, "send-keys", "-t", pane, "sleep 30", "Enter")
    assert _until(
        lambda: (
            _tmux(server, "display-message", "-p", "-t", pane, "#{pane_current_command}") == "sleep"
        )
    )

    assert tmux_restore.open_window(spot, str(tmp_path), {}) == (
        "",
        "its own pane is no longer idle at the shell it was found at",
    )
    assert _tmux(server, "display-message", "-p", "-t", pane, "#{pane_current_command}") == "sleep"


def test_two_lemons_crashed_in_one_pane_share_it_with_the_newest(server):
    pane = _tmux(server, "display-message", "-p", "#{pane_id}")
    older, newer = _row("claude:old", server, pane), _row("claude:new", server, pane)

    assert own_pane.idle([older, newer]) == {"claude:new": own_pane.idle([newer])["claude:new"]}
    placed, _ = tmux_restore.place([older, newer])
    assert {row.channel: spot.where for row, spot in placed}["claude:old"] != "work:0"


def test_a_script_running_in_the_shell_is_not_idle(server, tmp_path):
    pane = _tmux(server, "display-message", "-p", "#{pane_id}")
    shell = _tmux(server, "display-message", "-p", "-t", pane, "#{pane_pid}")
    [(_, spot)], _ = tmux_restore.place([_row("claude:a", server, pane)])
    marker = tmp_path / "started"
    _tmux(server, "send-keys", "-t", pane, f"sh -c 'touch {marker}; sleep 30; true'", "Enter")
    assert _until(marker.exists)

    assert tmux_restore.open_window(spot, str(tmp_path), {})[0] == ""
    assert _tmux(server, "display-message", "-p", "-t", pane, "#{pane_pid}") == shell


def test_a_shell_replaced_by_a_script_is_not_idle(server, tmp_path):
    pane = _tmux(server, "display-message", "-p", "#{pane_id}")
    [(_, spot)], _ = tmux_restore.place([_row("claude:a", server, pane)])
    marker = tmp_path / "started"
    _tmux(server, "send-keys", "-t", pane, f"exec sh -c 'touch {marker}; sleep 30; true'", "Enter")
    assert _until(marker.exists)

    assert tmux_restore.open_window(spot, str(tmp_path), {})[0] == ""
    assert own_pane.idle([_row("claude:b", server, pane)]) == {}


@pytest.mark.parametrize(
    ("argv", "interactive"),
    [
        ("-zsh", True),
        ("/bin/sh -i", True),
        ("fish --login", True),
        ("sh -c true", False),
        ("bash -ic true", False),
        ("sh script.sh", False),
    ],
)
def test_only_a_shell_running_nothing_is_interactive(argv, interactive):
    assert own_pane._interactive(argv) is interactive
