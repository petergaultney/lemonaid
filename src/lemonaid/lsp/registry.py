"""Where running `lemonaid lsp` servers say they are, and how a lemon's command reaches one.

Each server listens on a unix socket in lemonaid's state directory and writes a record
beside it. A request is one JSON object on one line, and so is its answer. This module
needs no `lsp` extra, so `lemonaid comments` and `lemonaid editor` work without it.
"""

import dataclasses
import hashlib
import json
import os
import socket
import typing as ty
from pathlib import Path

from ..front_end import location

_TIMEOUT_SECONDS: ty.Final = 10.0
# macOS limits a unix socket's path to 104 bytes, Linux to 108.
_MAX_SOCKET_PATH: ty.Final = 103


class Unreachable(Exception):
    """The server didn't answer: it exited, or it is stuck."""


@dataclasses.dataclass(frozen=True)
class Record:
    pid: int
    socket: str
    roots: tuple[str, ...]
    location: location.Location  # the editor's terminal, where the server started
    started: float

    def covers(self, path: Path) -> bool:
        return any(path.is_relative_to(root) for root in self.roots)


def text_digest(text: str) -> str:
    """What a request names a buffer's text by, to say which text it was computed from."""
    return hashlib.sha1(text.encode("utf-8", "surrogatepass")).hexdigest()


def directory() -> Path:
    state = os.environ.get("LEMONAID_STATE_DIR") or "~/.local/state/lemonaid"
    return Path(state).expanduser() / "lsp"


def socket_path(pid: int) -> Path | None:
    """Where server `pid` listens, or None when the state directory's path is too long
    for a socket."""
    path = directory() / f"{pid}.sock"
    return path if len(os.fsencode(path)) <= _MAX_SOCKET_PATH else None


def write(record: Record) -> None:
    directory().mkdir(parents=True, exist_ok=True)
    path = directory() / f"{record.pid}.json"
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(dataclasses.asdict(record)))
    temporary.replace(path)


def remove(pid: int) -> None:
    for suffix in (".json", ".sock"):
        (directory() / f"{pid}{suffix}").unlink(missing_ok=True)


def live() -> list[Record]:
    """Every server whose process still runs, newest first. A record whose process is gone
    is removed."""
    records = []
    for path in directory().glob("*.json"):
        try:
            data = json.loads(path.read_text())
            record = Record(
                **{
                    **data,
                    "roots": tuple(data["roots"]),
                    "location": location.Location(**data["location"]),
                }
            )
        except (OSError, ValueError, TypeError, KeyError):
            continue
        if _running(record.pid):
            records.append(record)
        else:
            remove(record.pid)
    return sorted(records, key=lambda r: r.started, reverse=True)


def by_preference(records: ty.Iterable[Record], caller: location.Location) -> list[Record]:
    """Servers in the caller's workspace (`location.near`) first, then the rest; newest
    first within each."""
    newest_first = sorted(records, key=lambda r: r.started, reverse=True)
    return sorted(newest_first, key=lambda r: not location.near(r.location, caller))


def request(record: Record, message: dict[str, ty.Any]) -> dict[str, ty.Any]:
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(_TIMEOUT_SECONDS)
            connection.connect(record.socket)
            connection.sendall(json.dumps(message).encode() + b"\n")
            answer = connection.makefile("rb").readline()
    except OSError as error:
        raise Unreachable(f"the editor server (pid {record.pid}) didn't answer: {error}") from None
    try:
        return json.loads(answer)
    except ValueError:
        raise Unreachable(f"the editor server (pid {record.pid}) closed the connection") from None


def _running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
