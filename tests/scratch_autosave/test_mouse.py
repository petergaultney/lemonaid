import fcntl
import os
import select
import struct
import subprocess
import termios
import time

from lemonaid.tmux import scratch, scratch_autosave
from tests.scratch_autosave.shared import settle, start


def _drain(fd, seconds=0.1):
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        ready, _, _ = select.select([fd], [], [], 0.01)
        if ready:
            os.read(fd, 65536)


def test_real_border_drag_and_cancelled_drag(tmux, monkeypatch):
    pane, _ = start(tmux, monkeypatch)
    tmux("set-option", "-g", "mouse", "on")
    socket = tmux("display", "-p", "#{socket_path}").stdout.strip()
    master, slave = os.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 90, 245, 0, 0))
    client = subprocess.Popen(
        ["tmux", "-S", socket, "attach", "-t", "a"],
        stdin=slave,
        stdout=slave,
        stderr=slave,
        env={**os.environ, "TERM": "xterm-256color"},
    )
    os.close(slave)
    try:
        _drain(master, 0.3)
        assert client.poll() is None
        observer = scratch_autosave.Observer()
        observer.poll(0)
        os.write(master, b"\x1b[<0;59;5M\x1b[<32;60;5M\x1b[<32;71;5M\x1b[<0;71;5m")
        _drain(master)
        assert tmux("display", "-pt", pane, "#{pane_width}").stdout.strip() == "70"
        settle(observer)
        assert scratch.saved_size("left") == "70"
        observer.poll(3)
        os.write(master, b"\x1b[<0;71;5M\x1b[<32;72;5M\x1b[<32;81;5M")
        _drain(master)
        observer.poll(4)
        os.write(master, b"\x1b[<32;71;5M\x1b[<0;71;5m")
        _drain(master)
        settle(observer, 5)
        assert scratch.saved_size("left") == "70"
        tmux("bind-key", "-n", "F6", "resize-pane", "-t", pane, "-x", "75")
        os.write(master, b"\x1b[17~")
        _drain(master, 0.6)
        assert tmux("display", "-pt", pane, "#{pane_width}").stdout.strip() == "75"
        settle(observer, 7)
        assert scratch.saved_size("left") == "75"
    finally:
        client.kill()
        client.wait(timeout=5)
        os.close(master)
