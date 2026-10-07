"""Private tmux servers and attached PTY clients for link tests."""

import os
import shutil
import subprocess
import tempfile
import time

import pytest

from lemonaid.inbox import db


@pytest.fixture
def server():
    if not shutil.which("tmux"):
        pytest.skip("tmux is not installed")

    with tempfile.TemporaryDirectory(prefix="lma-go-", dir="/tmp") as directory:
        command = ["tmux", "-S", f"{directory}/tmux.sock"]
        try:
            subprocess.run(
                [*command, "-f", "/dev/null", "new-session", "-d", "-s", "source"], check=True
            )
            yield command
        finally:
            subprocess.run([*command, "kill-server"], capture_output=True)


def _query(command, *args):
    return subprocess.check_output([*command, *args], text=True).strip()


def _record(command, target):
    location = _query(
        command,
        "display-message",
        "-p",
        "-t",
        target,
        "#{pane_id}|#{pane_tty}|#{session_name}|#{session_created}|#{start_time}|#{session_id}",
    ).split("|")
    pane, tty, session, created, started, session_id = location
    with db.connect() as conn:
        db.add(
            conn,
            "codex:real",
            "",
            switch_source="tmux",
            metadata={
                "tty": tty,
                "tmux_socket": command[2],
                "tmux_session": session,
                "tmux_session_order": [int(created), int(started), int(session_id.lstrip("$"))],
                "tmux_pane_identity": [pane, int(started)],
            },
        )
        return db.get_by_channel(conn, "codex:real")


@pytest.fixture
def clients(server):
    handles, processes = [], []

    def attach(session):
        master, slave = os.openpty()
        handles.extend([master, slave])
        env = {**os.environ, "TERM": "xterm-256color"}
        env.pop("TMUX", None)
        env.pop("TMUX_PANE", None)
        processes.append(
            subprocess.Popen(
                [*server, "attach-session", "-t", session],
                stdin=slave,
                stdout=slave,
                stderr=slave,
                env=env,
            )
        )
        for _ in range(100):
            names = _query(server, "list-clients", "-F", "#{client_name}|#{session_name}")
            if any(line.endswith(f"|{session}") for line in names.splitlines()):
                return
            time.sleep(0.01)
        pytest.fail("client did not attach")

    yield attach
    subprocess.run([*server, "kill-server"], capture_output=True)
    # Closing the PTYs releases clients even if their unread output filled the buffer.
    for handle in handles:
        os.close(handle)
    for process in processes:
        process.wait(timeout=5)
