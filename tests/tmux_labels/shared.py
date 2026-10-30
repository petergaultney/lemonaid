import contextlib
import subprocess
import tempfile
import time
from collections import abc
from pathlib import Path


@contextlib.contextmanager
def server() -> abc.Iterator[tuple[str, abc.Callable[..., str]]]:
    """A private tmux server with one session, `work`, in /tmp."""
    with tempfile.TemporaryDirectory(prefix="tl-", dir="/tmp") as directory:
        socket = str(Path(directory) / "sock")

        def tmux(*args: str) -> str:
            return subprocess.run(
                ["tmux", "-S", socket, *args], capture_output=True, text=True, check=True
            ).stdout.strip()

        tmux("-f", "/dev/null", "new-session", "-d", "-s", "work", "-c", "/tmp", "sleep", "600")
        try:
            yield socket, tmux
        finally:
            subprocess.run(["tmux", "-S", socket, "kill-server"], capture_output=True)


def until(condition, timeout: float = 10) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.05)
