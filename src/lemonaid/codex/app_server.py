"""A private `codex app-server` on stdio, asked JSON-RPC requests in batches.

It is never Codex's shared daemon: nothing else can reach it, and no Codex session runs in
it, so every Codex lemon keeps its own process and terminal.
"""

import contextlib
import itertools
import json
import os
import select
import shutil
import subprocess
import time
import typing as ty
from collections import abc

from ..log import get_logger

_log = get_logger("codex.app_server")

# Each start would otherwise sync the plugin catalog over the network into the Codex home.
_ARGV = (
    "app-server",
    *("--disable", "plugins", "--disable", "remote_plugin"),
    *("--disable", "plugin_discovery_prefetch"),
)

Call = tuple[str, dict[str, ty.Any]]  # (method, params)

# Set, no app-server is started. Each server has it set, since a `codex` that runs lemonaid's
# hooks under it is not one whose sessions are lemons, and a hook asking it about threads
# would start another. Tests set it too, so no test starts the developer's Codex.
NO_APP_SERVER = "LEMONAID_NO_CODEX_APP_SERVER"


class NoAnswer(Exception):
    pass


def _line(message: dict[str, ty.Any]) -> bytes:
    return json.dumps(message).encode() + b"\n"


class Server:
    """Use it from one thread at a time."""

    def __init__(self, proc: subprocess.Popen) -> None:
        assert proc.stdin and proc.stdout
        self._proc = proc
        self._ids = itertools.count(1)
        self._buffer = b""
        self._unsent = bytearray()
        os.set_blocking(proc.stdin.fileno(), False)

    def _replies(self, outgoing: bytearray, deadline: float) -> abc.Iterator[dict[str, ty.Any]]:
        """Replies, while *outgoing* is written. Writing and reading share *deadline*, so a
        server that stops reading its input can't block the caller on a full pipe."""
        assert self._proc.stdin and self._proc.stdout
        stdin, stdout = self._proc.stdin.fileno(), self._proc.stdout.fileno()
        while True:
            while b"\n" in self._buffer:
                line, _, self._buffer = self._buffer.partition(b"\n")
                if line.strip() and "id" in (message := json.loads(line)):
                    yield message

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise NoAnswer("timed out")

            readable, writable, _ = select.select(
                [stdout], [stdin] if outgoing else [], [], remaining
            )
            if not readable and not writable:
                raise NoAnswer("timed out")

            if writable:
                with contextlib.suppress(BlockingIOError):
                    del outgoing[: os.write(stdin, outgoing)]
            if readable:
                chunk = os.read(stdout, 1 << 16)
                if not chunk:
                    raise NoAnswer(f"exited with {self._proc.poll()}")

                self._buffer += chunk

    def ask(self, calls: abc.Sequence[Call], timeout: float) -> list[dict[str, ty.Any]]:
        """Each call's reply, `result` or `error`, in the order of *calls*."""
        ids = [next(self._ids) for _ in calls]
        outgoing = self._unsent + b"".join(
            _line({"id": number, "method": method, "params": params})
            for number, (method, params) in zip(ids, calls, strict=True)
        )
        self._unsent = bytearray()
        wanted = set(ids)
        replies: dict[int, dict[str, ty.Any]] = {}
        for reply in self._replies(outgoing, time.monotonic() + timeout):
            if reply["id"] in wanted:
                replies[reply["id"]] = reply
            if len(replies) == len(ids):
                break
        return [replies[number] for number in ids]

    def notify(self, method: str) -> None:
        """Send a notification ahead of the next batch of calls."""
        self._unsent += _line({"method": method})

    def alive(self) -> bool:
        return self._proc.poll() is None

    def close(self) -> None:
        self._proc.kill()
        self._proc.wait()


def start(timeout: float) -> Server | None:
    """A server that has answered `initialize`, or None when Codex isn't installed or
    doesn't answer within *timeout*."""
    codex = shutil.which("codex")
    if codex is None or os.environ.get(NO_APP_SERVER):
        return None

    try:
        proc = subprocess.Popen(
            [codex, *_ARGV],
            env={**os.environ, NO_APP_SERVER: "1"},
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0,
        )
    except OSError as error:
        _log.warning("could not start codex app-server: %s", error)
        return None

    server = Server(proc)
    try:
        [reply] = server.ask(
            [("initialize", {"clientInfo": {"name": "lemonaid", "version": "0"}})], timeout
        )
        if "error" in reply:
            raise NoAnswer(str(reply["error"]))

        server.notify("initialized")
    except (NoAnswer, OSError, ValueError, KeyError, TypeError) as error:
        _log.warning("codex app-server did not start: %s", error)
        server.close()
        return None

    return server


_Answer = ty.TypeVar("_Answer")


def once(
    question: abc.Callable[[Server], _Answer], about: str, unanswered: _Answer, timeout: float
) -> _Answer:
    """*question* asked of a short-lived server, or *unanswered* when it can't be."""
    server = start(timeout)
    if server is None:
        return unanswered

    try:
        return question(server)
    except (NoAnswer, OSError, ValueError, KeyError, TypeError) as error:
        _log.warning("codex app-server did not answer about %s: %s", about, error)
        return unanswered
    finally:
        server.close()
