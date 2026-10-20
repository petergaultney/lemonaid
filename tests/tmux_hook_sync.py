"""Synchronize private-server tests with tmux's asynchronous notification hooks."""

import socket
import subprocess
import time
from collections import abc

_BUSY = "@lemonaid_test_hook_busy"


def _wait(predicate: abc.Callable[[], bool], description: str) -> None:
    deadline = time.monotonic() + 5
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError(f"Timed out waiting for {description}")
        time.sleep(0.01)


def _command(name: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["tmux", "-L", name, *args], capture_output=True, text=True)


def _idle(name: str) -> bool:
    return _command(name, "show-option", "-gqv", _BUSY).stdout.strip() in ("", "0")


def _stopped(path: str) -> bool:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        return connection.connect_ex(path) != 0


def run(name: str, *args: str) -> subprocess.CompletedProcess[str]:
    _wait(lambda: _idle(name), "tmux notification hooks")
    socket_path = (
        _command(name, "display", "-p", "#{socket_path}").stdout.strip()
        if args == ("kill-server",)
        else ""
    )
    result = _command(name, *args)
    if socket_path and result.returncode == 0:
        _wait(lambda: _stopped(socket_path), "tmux server shutdown")
    else:
        _wait(lambda: _idle(name), "tmux notification hooks")
    return result


def install(name: str, hooks: tuple[str, ...]) -> None:
    for hook in hooks:
        for index, value in ((0, "1"), (999, "0")):
            _command(
                name, "set-hook", "-g", f"{hook}[{index}]", f"set-option -g {_BUSY} {value}"
            ).check_returncode()


def attached(name: str) -> None:
    _wait(lambda: bool(_command(name, "list-clients").stdout.strip()), "control client attachment")
