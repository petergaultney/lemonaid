import contextlib
import shutil
import tempfile
from pathlib import Path

import pytest

from lemonaid.launch.restart import pane


@pytest.fixture
def server(tmp_path):
    if not shutil.which("tmux"):
        pytest.skip("tmux unavailable")
    directory = tempfile.TemporaryDirectory(prefix="restart-", dir="/tmp")
    socket = str(Path(directory.name) / "tmux")
    try:
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
        yield pane.locate(socket, tty)
    finally:
        with contextlib.suppress(ValueError):
            pane.run(socket, "kill-server")
        directory.cleanup()
