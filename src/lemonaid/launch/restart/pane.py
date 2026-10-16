"""Socket-explicit pane inspection and guarded replacement."""

import dataclasses
import time

from ...claude import launch_args
from .. import window
from . import process


@dataclasses.dataclass(frozen=True)
class Pane:
    socket: str
    pane: str
    window: str
    tty: str
    pid: int
    dead: bool
    cwd: str


def run(socket: str, *args: str) -> str:
    result = window.server_command(socket, *args)
    if result.returncode:
        raise ValueError(f"tmux: {(result.stderr or result.stdout).strip()}")

    return result.stdout.rstrip("\n")


def locate(socket: str, tty: str) -> Pane:
    if not socket or not tty:
        raise ValueError("Restart needs a recorded tmux socket and terminal")

    rows = run(
        socket,
        "list-panes",
        "-a",
        "-F",
        "#{pane_id}\t#{window_id}\t#{pane_tty}\t#{pane_pid}\t#{pane_dead}\t#{pane_current_path}",
    )
    found = [line.split("\t", 5) for line in rows.splitlines() if line.split("\t")[2] == tty]
    if len(found) != 1:
        raise ValueError("The recorded terminal does not identify exactly one pane on its server")

    p, w, t, pid, dead, cwd = found[0]
    return Pane(socket, p, w, t, int(pid), dead == "1", cwd)


def check(expected: Pane) -> Pane:
    current = by_id(expected.socket, expected.pane)
    if (current.pane, current.window, current.pid) != (
        expected.pane,
        expected.window,
        expected.pid,
    ):
        raise ValueError("The reserved pane changed; refusing to replace it")

    return current


def by_id(socket: str, pane_id: str) -> Pane:
    fields = run(
        socket,
        "display-message",
        "-p",
        "-t",
        pane_id,
        "#{pane_id}\t#{window_id}\t#{pane_tty}\t#{pane_pid}\t#{pane_dead}\t#{pane_current_path}",
    ).split("\t", 5)
    if len(fields) != 6 or fields[0] != pane_id:
        raise ValueError("The reserved pane no longer exists")

    p, w, t, pid, dead, cwd = fields
    return Pane(socket, p, w, t, int(pid), dead == "1", cwd)


def exit_option(target: Pane) -> str:
    # Empty output means inheritance, distinct from a local value equal to its parent.
    return run(target.socket, "show-options", "-p", "-v", "-t", target.pane, "remain-on-exit")


def preserve(target: Pane) -> None:
    check(target)
    run(target.socket, "set-option", "-p", "-t", target.pane, "remain-on-exit", "on")


def restore(target: Pane, previous: str) -> None:
    check(target)
    run(
        target.socket,
        "set-option",
        "-p",
        *([] if previous else ["-u"]),
        "-t",
        target.pane,
        "remain-on-exit",
        *([previous] if previous else []),
    )


def replace(
    target: Pane, root: process.Identity, cwd: str, line: str, environment: dict[str, str]
) -> Pane:
    current = check(target)
    deadline = time.monotonic() + 3
    remaining = process.on_tty(target.tty)
    shell_root = process.shell(root, launch_args.argv(root.pid))
    expected = [root] if not current.dead and shell_root else []
    while remaining != expected and time.monotonic() < deadline:
        time.sleep(0.05)
        current = check(target)
        expected = [root] if not current.dead and shell_root else []
        remaining = process.on_tty(target.tty)
    if remaining != expected:
        raise ValueError("Unmanaged jobs remain on the terminal; refusing to respawn the pane")

    if not current.dead and not process.same(root):
        raise ValueError("Original shell generation changed")

    if not current.dead and not process.shell(root, launch_args.argv(root.pid)):
        raise ValueError("Only the captured interactive shell can be replaced while alive")

    run(
        target.socket,
        "respawn-pane",
        *([] if current.dead else ["-k"]),
        "-t",
        target.pane,
        "-c",
        cwd,
        *(part for key, value in environment.items() for part in ("-e", f"{key}={value}")),
        line,
    )
    replacement = by_id(target.socket, target.pane)
    if replacement.window != target.window:
        raise ValueError("The reserved pane moved to another window during replacement")

    return replacement
