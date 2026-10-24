import os
import pty
import shutil
import subprocess
import time
import uuid

import pytest

from lemonaid.tmux import fast_popup, popup_binding


def _until(check, seconds: float = 5.0) -> bool:
    deadline = time.monotonic() + seconds
    while not check():
        if time.monotonic() > deadline:
            return False
        time.sleep(0.02)
    return True


def _attach(server: list[str], session: str) -> tuple[int, int]:
    pid, terminal = pty.fork()
    if pid == 0:
        os.environ.pop("TMUX", None)
        os.environ["TERM"] = "xterm-256color"
        os.execvp("tmux", [*server, "attach-session", "-t", session])
    return pid, terminal


def test_the_binding_shows_the_resident_on_one_client_at_a_time_and_closes_it_from_inside(
    tmp_path,
):
    if not shutil.which("tmux"):
        pytest.skip("tmux not installed")

    server = ["tmux", "-L", f"lemonaid-test-{uuid.uuid4().hex[:8]}"]

    def tmux(*args: str) -> str:
        return subprocess.run([*server, *args], capture_output=True, text=True).stdout.strip()

    def popup_clients() -> list[str]:
        return tmux("list-clients", "-t", "=_lma_probe:", "-F", "#{client_name}").split()

    def sessions_with_clients() -> list[str]:
        return tmux("list-clients", "-F", "#{client_session}").split()

    tmux("-f", "/dev/null", "new-session", "-d", "-s", "main", "-x", "120", "-y", "40")
    tmux("new-session", "-d", "-s", fast_popup.session_for("probe"), "sleep 600")
    conf = tmp_path / "binding.conf"
    conf.write_text(popup_binding.binding("probe", "Space", 2, " probe ") + "\n")
    tmux("source-file", str(conf))
    tmux("new-session", "-d", "-s", "other", "-x", "120", "-y", "40")
    clients = [_attach(server, "main"), _attach(server, "other")]
    try:
        assert _until(lambda: sorted(sessions_with_clients()) == ["main", "other"])
        (a, b) = (
            tmux("list-clients", "-t", session, "-F", "#{client_name}")
            for session in ("main", "other")
        )
        os.write(clients[0][1], b"\x02 ")
        assert _until(lambda: sorted(sessions_with_clients()) == ["_lma_probe", "main", "other"])
        assert tmux("show-option", "-t", "=_lma_probe:", "-qv", fast_popup.OPENER_OPTION) == a
        (first_popup,) = popup_clients()
        os.write(clients[1][1], b"\x02 ")  # B takes the popup over: A's closes
        assert _until(
            lambda: tmux("show-option", "-t", "=_lma_probe:", "-qv", fast_popup.OPENER_OPTION) == b
        )
        assert _until(lambda: (now := popup_clients()) != [first_popup] and len(now) == 1)
        os.write(clients[1][1], b"\x02 ")
        assert _until(lambda: sorted(sessions_with_clients()) == ["main", "other"])
    finally:
        for pid, _ in clients:
            os.kill(pid, 9)
        tmux("kill-server")
