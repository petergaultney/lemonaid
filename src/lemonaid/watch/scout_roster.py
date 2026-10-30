"""The lemons whose push scouts the scout host runs: one registration file each.

`watch --self --push` writes a lemon's registration and the host runs a scout for every
registration it finds. Removing the file stops that lemon's scout. A host serves only
registrations written against the same database, state and Claude directory as its own,
so a sandbox or test never delivers through another environment's sessions.
"""

import contextlib
import fcntl
import json
import os
import pathlib
import typing as ty
import uuid
from collections import abc

from ..claude import session_socket
from ..inbox import db
from ..log import get_logger
from . import wait_state, waiter_lock

_log = get_logger("watch.scout_roster")


class Registration(ty.NamedTuple):
    lemon_id: str
    channel: str  # claude:<session> or codex:<thread>
    thread: str  # the Codex thread the scout queues into; "" for a Claude session
    cwd: str
    environment: str
    token: str  # changes whenever the registration is written, so a host restarts the scout


def _state() -> pathlib.Path:
    return pathlib.Path(
        os.environ.get("LEMONAID_STATE_DIR") or "~/.local/state/lemonaid"
    ).expanduser()


def _dir() -> pathlib.Path:
    return _state() / "scouts"


def host_lock_path() -> pathlib.Path:
    return _state() / "scout-host.lock"


def log_path() -> pathlib.Path:
    """Where the host and every scout it runs write their output."""
    return _state() / "push-scout.log"


def environment() -> str:
    """The files this process's lemonaid reads and delivers through."""
    return json.dumps([str(db.get_db_path()), str(_state()), str(session_socket.claude_dir())])


def path(lemon_id: str) -> pathlib.Path:
    return _dir() / f"{lemon_id}.json"


@contextlib.contextmanager
def _changing(lemon_id: str) -> abc.Iterator[None]:
    """Held while a registration is replaced or removed, so a removal of an old one never
    deletes the new one written between its check and its unlink."""
    _dir().mkdir(parents=True, exist_ok=True)
    with path(lemon_id).with_suffix(".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def register(lemon_id: str, channel: str, thread: str, cwd: str) -> Registration:
    registration = Registration(lemon_id, channel, thread, cwd, environment(), uuid.uuid4().hex)
    with _changing(lemon_id):
        temporary = path(lemon_id).with_suffix(f".{registration.token}.tmp")
        temporary.write_text(json.dumps(registration._asdict()))
        temporary.replace(path(lemon_id))
    return registration


def read(lemon_id: str) -> Registration | None:
    return _load(path(lemon_id))


def _load(path: pathlib.Path) -> Registration | None:
    try:
        return Registration(**json.loads(path.read_text()))
    except FileNotFoundError:
        return None
    except (OSError, ValueError, TypeError) as error:
        _log.warning("unreadable scout registration %s: %s", path, error)
        return None


def listed() -> dict[str, Registration]:
    found = (_load(path) for path in sorted(_dir().glob("*.json")))
    return {r.lemon_id: r for r in found if r is not None}


def remove(lemon_id: str, token: str = "", by: str = "") -> None:
    """Stop *lemon_id*'s scout; with *token*, only if its registration is still that one."""
    with _changing(lemon_id):
        current = read(lemon_id)
        if current is None or (token and current.token != token):
            return

        path(lemon_id).unlink(missing_ok=True)
    if by:
        _log.info("%s removed the scout registration of %s", by, lemon_id)


def host_pid() -> int:
    """The running host's pid, or 0."""
    if not waiter_lock.held(host_lock_path()):
        return 0

    holder = waiter_lock.lock_holder(host_lock_path()).split()
    return int(holder[1]) if len(holder) > 1 and holder[0] == "pid" and holder[1].isdigit() else 0


def serving(lemon_id: str, host: int) -> bool:
    """Whether the host with pid *host* holds *lemon_id*'s lock, as it does while running its scout."""
    lock = wait_state.lock_path(lemon_id)
    return (
        bool(host)
        and waiter_lock.held(lock)
        and waiter_lock.lock_holder(lock).startswith(f"pid {host} ")
    )
