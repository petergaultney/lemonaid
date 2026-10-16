"""Process generations, checked independently of terminal and inbox liveness."""

import dataclasses
import os
import signal
import subprocess
import time
from pathlib import Path

SHELLS = frozenset({"sh", "bash", "zsh", "fish", "xonsh", "nu", "dash"})


@dataclasses.dataclass(frozen=True)
class Identity:
    pid: int
    parent: int
    tty: str
    started: str
    executable: str


def shell(identity: Identity, argv: list[str]) -> bool:
    name = Path(identity.executable).name
    return name in SHELLS or (
        name.startswith("python")
        and (
            (len(argv) > 1 and Path(argv[1]).name in ("xonsh", "xonsh.py"))
            or argv[1:3] == ["-m", "xonsh"]
        )
    )


def inspect(pid: int) -> Identity | None:
    result = subprocess.run(
        ["ps", "-p", str(pid), "-o", "ppid=,tty=,lstart=,stat=,comm="],
        capture_output=True,
        text=True,
        timeout=3,
        check=False,
    )
    fields = result.stdout.strip().split(None, 8)
    if result.returncode or len(fields) != 9 or fields[7].startswith("Z"):
        return None

    return Identity(pid, int(fields[0]), fields[1], " ".join(fields[2:7]), fields[8])


def ancestry(pid: int) -> list[Identity]:
    found: list[Identity] = []
    for _ in range(64):
        entry = inspect(pid)
        if entry is None or entry.pid <= 1 or entry in found:
            break

        found.append(entry)
        pid = entry.parent
    return found


def same(identity: Identity) -> bool:
    return inspect(identity.pid) == identity


def terminate(identity: Identity, timeout: float = 10) -> None:
    if not same(identity):
        raise ValueError("Harness process generation changed before SIGTERM")

    os.kill(identity.pid, signal.SIGTERM)
    deadline = time.monotonic() + timeout
    while same(identity):
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"PID {identity.pid} did not exit after SIGTERM; no replacement started"
            )

        time.sleep(0.05)


def on_tty(tty: str) -> list[Identity]:
    result = subprocess.run(
        ["ps", "-t", tty.removeprefix("/dev/"), "-o", "pid="],
        capture_output=True,
        text=True,
        timeout=3,
        check=False,
    )
    if result.returncode and result.stderr.strip() and "no processes found" not in result.stderr:
        if not Path(tty).exists() and any(
            text in result.stderr
            for text in ("No such file or directory", "TTY could not be found")
        ):
            return []

        raise ValueError(f"Cannot inventory terminal processes: {result.stderr.strip()}")

    return [entry for pid in result.stdout.split() if (entry := inspect(int(pid))) is not None]


def descendants(pid: int) -> list[Identity]:
    """Include tool jobs that detached from the pane's controlling terminal."""
    result = subprocess.run(
        ["ps", "-A", "-o", "pid=,ppid="], capture_output=True, text=True, timeout=3, check=True
    )
    parents = {
        int(child): int(parent)
        for line in result.stdout.splitlines()
        for child, parent in [line.split()]
    }
    found = {pid}
    for _ in range(64):
        children = {child for child, parent in parents.items() if parent in found}
        if children <= found:
            return [
                entry for child in sorted(found - {pid}) if (entry := inspect(child)) is not None
            ]
        found |= children
    raise ValueError("Cannot bound the harness's descendant tree")
