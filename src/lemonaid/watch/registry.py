"""Every running waiter, under the lemon that started it, so a lemon can stop only its own.

A waiter keeps `<pid>.json` in the registry locked for as long as it runs. A file
nobody holds is a waiter that is gone, so a stop signals only a pid whose own
process still holds its entry.
"""

import contextlib
import dataclasses
import json
import os
import pathlib
import shlex
import signal
import sys
import threading
import time
import typing as ty
from collections import abc

from ..brief import lemon
from ..inbox import db
from ..inbox.channel import full_channel_id
from . import waiter_lock

KINDS = ("inbox", "pr", "doc", "file", "briefs")


@dataclasses.dataclass(frozen=True)
class Waiter:
    pid: int
    channel: str  # the lemon that started it; "" when it had no identity
    kind: str
    targets: tuple[str, ...]  # what it watches: a Lemon-ID, `owner/repo#12`, absolute paths
    command: str  # the command that rearms it
    cwd: str
    repo: str = ""


def _registry() -> pathlib.Path:
    state = os.environ.get("LEMONAID_STATE_DIR") or "~/.local/state/lemonaid"
    return pathlib.Path(state).expanduser() / "waiters"


def owner_channel(explicit: str = "", codex_thread: str = "") -> str:
    """The caller's channel, or "" when it has none."""
    if codex_thread:
        return full_channel_id("codex", codex_thread)

    with db.connect() as conn:
        try:
            return lemon.self_channel(conn, explicit)
        except LookupError:
            return ""


def _stopped_message(waiter: Waiter) -> str:
    return (
        f"This {waiter.kind} waiter ({', '.join(waiter.targets)}) was stopped by SIGTERM. "
        "If you didn't stop it yourself, another process did: rearm it with "
        f"`{waiter.command}`."
    )


@contextlib.contextmanager
def _reports_termination(message: str) -> abc.Iterator[None]:
    """Prints `message` to stderr and exits 143 if SIGTERM arrives.

    A harness reports a killed background task only by its exit code, so without
    this a lemon whose waiter another process killed cannot tell why it woke.
    Signal handlers belong to the main thread; elsewhere this does nothing.
    """
    if threading.current_thread() is not threading.main_thread():
        yield
        return

    def _exit(signum: int, _frame: object) -> None:
        print(message, file=sys.stderr, flush=True)
        raise SystemExit(128 + signum)

    previous = signal.signal(signal.SIGTERM, _exit)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, previous)


@contextlib.contextmanager
def registered(
    kind: str, targets: abc.Iterable[str], channel: str, command: str, repo: str = ""
) -> abc.Iterator[Waiter]:
    """Lists this process as a running waiter until the block exits."""
    waiter = Waiter(
        os.getpid(), channel, kind, tuple(targets), command, str(pathlib.Path.cwd()), repo
    )
    _registry().mkdir(parents=True, exist_ok=True)
    path = _registry() / f"{waiter.pid}.json"
    lock = waiter_lock.acquire(path)
    if lock is None:
        raise RuntimeError(f"{path} is held by another process")

    try:
        lock.truncate(0)
        lock.write(json.dumps(dataclasses.asdict(waiter)))
        lock.flush()
        with _reports_termination(_stopped_message(waiter)):
            yield waiter
    finally:
        path.unlink(missing_ok=True)
        lock.close()


def _read(path: pathlib.Path) -> Waiter | None:
    try:
        saved = json.loads(path.read_text())
        waiter = Waiter(**{**saved, "targets": tuple(saved["targets"])})
    except (OSError, ValueError, TypeError, KeyError):
        return None  # gone, or its process has not written it yet
    return waiter if str(waiter.pid) == path.stem else None


def _alive(pid: str) -> bool:
    try:
        os.kill(int(pid), 0)
    except (ValueError, ProcessLookupError):
        return False
    except PermissionError:
        return True

    return True


def _running() -> abc.Iterator[Waiter]:
    for path in sorted(_registry().glob("*.json")):
        if not waiter_lock.held(path):
            if not _alive(path.stem):
                path.unlink(missing_ok=True)  # its process exited without removing it
            continue

        if waiter := _read(path):
            yield waiter


def _matches(waiter: Waiter, target: str) -> bool:
    if not target:
        return True

    candidates = {target, str(pathlib.Path(target).expanduser().resolve())}
    return any(t in candidates or t.endswith(f"#{target}") for t in waiter.targets)


def mine(channel: str, kind: str = "", target: str = "") -> list[Waiter]:
    """`channel`'s running waiters, of `kind` and watching `target` when given."""
    if not channel:
        return []

    return [
        waiter
        for waiter in _running()
        if waiter.channel == channel and kind in ("", waiter.kind) and _matches(waiter, target)
    ]


def stop(waiter: Waiter, grace: float = 2.0) -> None:
    """SIGTERMs `waiter` if it still holds its entry, then waits up to `grace` seconds for it."""
    path = _registry() / f"{waiter.pid}.json"
    if not waiter_lock.held(path):
        return

    try:
        os.kill(waiter.pid, signal.SIGTERM)
    except ProcessLookupError:
        return

    deadline = time.monotonic() + grace
    while waiter_lock.held(path):
        if time.monotonic() >= deadline:
            raise TimeoutError(f"{waiter.kind} waiter pid {waiter.pid} did not exit")

        time.sleep(0.05)


def watching(
    a: ty.Any, kind: str, targets: abc.Iterable[str], codex_thread: str = "", repo: str = ""
) -> ty.ContextManager[Waiter]:
    """`registered` for a waiter started from the CLI arguments `a`."""
    return registered(
        kind,
        targets,
        owner_channel(getattr(a, "channel", "") or "", codex_thread),
        shlex.join(getattr(a, "invocation", None) or ["lemonaid", *sys.argv[1:]]),
        repo,
    )
