"""Every running waiter, under the lemon that started it, so a lemon can stop only its own.

A waiter keeps `<pid>.json` in the registry locked for as long as it runs. A file
nobody holds is a waiter that is gone, so a stop signals only a pid whose own
process still holds its entry.
"""

import contextlib
import dataclasses
import functools
import json
import os
import pathlib
import shlex
import sqlite3
import sys
import time
import typing as ty
from collections import abc

from ..brief import lemon
from ..codex import channels
from ..inbox import db
from . import scout_roster, stop_sender, termination, waiter_lock

KINDS = ("wait", "inbox", "pr", "repo", "doc", "file", "briefs")


@dataclasses.dataclass(frozen=True)
class Waiter:
    pid: int
    channel: str  # the lemon that started it; "" when it had no identity
    kind: str
    targets: tuple[str, ...]  # what it watches: a Lemon-ID, `owner/repo#12`, absolute paths
    command: str  # the command that rearms it
    cwd: str
    repo: str = ""
    version: str = ""  # lemonaid's, when the waiter started
    restartable: bool = False  # whether it restarts on `restart.SIGNAL`, which kills others
    prefix: str = ""  # `sys.prefix` of the install it runs from
    code: str = ""  # digest of the lemonaid modules it loaded (see `restart.fingerprint`)
    code_paths: tuple[str, ...] = ()
    started: float = 0.0  # when it registered; a restart in place registers again
    hosted: bool = False  # a push scout the scout host runs; `pid` is the host's


def root() -> pathlib.Path:
    state = os.environ.get("LEMONAID_STATE_DIR") or "~/.local/state/lemonaid"
    return pathlib.Path(state).expanduser()


def _registry() -> pathlib.Path:
    return root() / "waiters"


def entry(pid: int) -> pathlib.Path:
    """The registry file the waiter with `pid` holds locked while it runs."""
    return _registry() / f"{pid}.json"


def owner_channel(explicit: str = "", codex_thread: str = "") -> str:
    """The caller's channel, or "" when it has none."""
    with db.connect() as conn:
        if codex_thread:
            return channels.for_session(conn, codex_thread)

        try:
            return lemon.self_channel(conn, explicit)
        except LookupError:
            return ""


@contextlib.contextmanager
def registered(
    kind: str,
    targets: abc.Iterable[str],
    channel: str,
    command: str,
    repo: str = "",
    *,
    version: str = "",
    restartable: bool = False,
    code: tuple[str, tuple[str, ...]] = ("", ()),
) -> abc.Iterator[Waiter]:
    """Lists this process as a running waiter until the block exits."""
    waiter = Waiter(
        os.getpid(),
        channel,
        kind,
        tuple(targets),
        command,
        str(pathlib.Path.cwd()),
        repo,
        version,
        restartable,
        sys.prefix,
        *code,
        started=time.time(),
    )
    _registry().mkdir(parents=True, exist_ok=True)
    path = entry(waiter.pid)
    lock = waiter_lock.acquire(path)
    if lock is None:
        raise RuntimeError(f"{path} is held by another process")

    try:
        stop_sender.clear(path)  # left by an earlier process with this pid
        lock.truncate(0)
        lock.write(json.dumps(dataclasses.asdict(waiter)))
        lock.flush()
        with termination.reported(
            lambda: termination.stopped_message(
                waiter.kind, waiter.targets, waiter.command, stop_sender.describe(path)
            ),
            entry(waiter.pid),
        ):
            yield waiter
    finally:
        stop_sender.clear(path)
        path.unlink(missing_ok=True)
        lock.close()


def _read(path: pathlib.Path) -> Waiter | None:
    try:
        saved = json.loads(path.read_text())
        known = {f.name for f in dataclasses.fields(Waiter)} - {"targets", "code_paths"}
        waiter = Waiter(
            **{k: v for k, v in saved.items() if k in known},
            targets=tuple(saved["targets"]),
            code_paths=tuple(saved.get("code_paths", ())),
        )
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


def _hosted() -> abc.Iterator[Waiter]:
    host = scout_roster.host_pid()
    for r in scout_roster.listed().values() if host else ():
        if scout_roster.serving(r.lemon_id, host):
            yield Waiter(
                host,
                r.channel,
                "wait",
                (r.lemon_id,),
                "lemonaid watch --self" + (" --codex-thread" if r.thread else "") + " --push",
                r.cwd,
                hosted=True,
            )


def running() -> abc.Iterator[Waiter]:
    """Every running waiter, each push scout the scout host runs included."""
    yield from _hosted()
    for path in sorted(_registry().glob("*.json")):
        if not waiter_lock.held(path):
            if not _alive(path.stem):
                path.unlink(missing_ok=True)  # its process exited without removing it
                stop_sender.clear(path)
            continue

        if waiter := _read(path):
            yield waiter


def current(waiter: Waiter) -> bool:
    """Whether *waiter*'s process still runs and holds the entry it was read from."""
    if waiter.hosted:
        return waiter in _hosted()

    path = entry(waiter.pid)
    return waiter_lock.held(path) and _read(path) == waiter


def _matches(waiter: Waiter, target: str) -> bool:
    if not target:
        return True

    candidates = {target, str(pathlib.Path(target).expanduser().resolve())}
    return any(t in candidates or t.endswith(f"#{target}") for t in waiter.targets)


def _owner(conn: sqlite3.Connection, channel: str) -> str:
    return channels.for_session(conn, channel[6:]) if channel.startswith("codex:") else channel


def mine(channel: str, kind: str = "", target: str = "") -> list[Waiter]:
    """`channel`'s running waiters, of `kind` and watching `target` when given."""
    if not channel:
        return []

    with db.connect() as conn:
        owner = _owner(conn, channel)
        return [
            waiter
            for waiter in running()
            if _owner(conn, waiter.channel) == owner
            and kind in ("", waiter.kind)
            and _matches(waiter, target)
        ]


def by_lemon(conn: sqlite3.Connection) -> abc.Callable[[str], list[Waiter]]:
    """`mine` for many channels, listing the running waiters and resolving each channel once."""
    owner = functools.cache(functools.partial(_owner, conn))
    found: dict[str, list[Waiter]] = {}
    for waiter in running():
        found.setdefault(owner(waiter.channel), []).append(waiter)
    return lambda channel: list(found.get(owner(channel), [])) if channel else []


def running_for(kind: str, target: str) -> list[Waiter]:
    """Running waiters of `kind` watching `target`, whichever lemon started them."""
    return [w for w in running() if w.kind == kind and target in w.targets]


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
