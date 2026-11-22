import os
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest

from lemonaid.grove.window import control


def test_a_request_shows_over_its_client_or_hides_and_an_unknown_one_does_neither():
    done = []

    for line in ("show /dev/ttys004\n", "show\n", "hide\n", "raise\n", "\n"):
        control.dispatch(
            line, show=lambda client: done.append(client), hide=lambda: done.append("hidden")
        )

    assert done == ["/dev/ttys004", "", "hidden"]


def test_the_binding_summons_the_window_on_macos_and_starts_it_when_it_isnt_running():
    darwin, mac_bind, other, other_bind, end = control.binding("G").splitlines()

    assert darwin == "if-shell 'test \"$(uname -s)\" = Darwin' {"
    assert mac_bind.startswith(
        '  bind-key G run-shell -b \'S="${LEMONAID_STATE_DIR:-$HOME/.local/state/lemonaid}/grove-window.sock"; '
    )
    assert 'echo "show #{client_tty}" | nc -U "$S"' in mac_bind
    assert 'tmux new-session -d -s _lma_grove_window "lemonaid grove window run"' in mac_bind
    assert "sleep 3" not in mac_bind  # it waits for the window to listen instead
    assert (other, other_bind, end) == (
        "} {",
        "  bind-key G run-shell -b 'lemonaid tmux popup grove'",
        "}",
    )


def test_send_delivers_one_line_and_fails_with_nobody_listening():
    path = Path(tempfile.mkdtemp(dir="/tmp")) / "w.sock"  # short: a socket path has a length limit
    got = []

    class Handler(socketserver.StreamRequestHandler):
        def handle(self) -> None:
            got.append(self.rfile.readline().decode())

    with socketserver.UnixStreamServer(str(path), Handler) as server:
        serving = threading.Thread(target=server.handle_request, daemon=True)
        serving.start()
        control.send("show /dev/ttys001", path)
        serving.join(timeout=5)

    assert got == ["show /dev/ttys001\n"]
    path.unlink()
    try:
        control.send("show", path)
    except OSError:
        return
    raise AssertionError("send should fail with no window listening")


_FAKE_TMUX = """#!/bin/sh
echo "$*" >> "$LEMONAID_STATE_DIR/tmux-calls"
[ "$1" = new-session ] && "$PYTHON" "$LEMONAID_STATE_DIR/window.py" &
exit 0
"""

_FAKE_WINDOW = """import socket, sys, time
from pathlib import Path
here = Path(sys.argv[0]).parent
time.sleep(0.5)  # starting up
with socket.socket(socket.AF_UNIX) as server:
    server.bind(str(here / "grove-window.sock"))
    server.listen()
    server.settimeout(10)
    conn, _ = server.accept()
    (here / "shown").write_bytes(conn.makefile("rb").readline())
    conn.close()
"""


@pytest.mark.skipif(sys.platform != "darwin", reason="the binding starts the window only on macOS")
def test_the_binding_shows_a_window_it_starts_as_soon_as_it_listens():
    state = Path(tempfile.mkdtemp(dir="/tmp"))  # short: a socket path has a length limit
    (state / "tmux").write_text(_FAKE_TMUX)
    (state / "tmux").chmod(0o755)
    (state / "window.py").write_text(_FAKE_WINDOW)
    mac_bind = control.binding("G").splitlines()[1]
    shell = mac_bind[mac_bind.index("-b '") + 4 : -1].replace("#{client_tty}", "/dev/ttys009")
    env = {
        **os.environ,
        "LEMONAID_STATE_DIR": str(state),
        "PATH": f"{state}:{os.environ['PATH']}",
        "PYTHON": sys.executable,
    }

    began = time.monotonic()
    subprocess.run(["sh", "-c", shell], env=env, timeout=15, check=True)
    assert (state / "shown").read_text() == "show /dev/ttys009\n"
    assert time.monotonic() - began < 2.5
    assert (
        (state / "tmux-calls")
        .read_text()
        .startswith("new-session -d -s _lma_grove_window lemonaid grove window run")
    )
