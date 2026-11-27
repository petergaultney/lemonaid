"""Serve lemonaid's watch-source protocol on stdin and stdout until stdin closes
(docs/source-plugins.md).

A thread beside the request loop turns the gateway's wake files into `ready <id>` notices,
keeps each followed conversation's interest file fresh, and holds the gateway socket while
anything is followed.
"""

import json
import logging
import sys
import threading
import time
import typing as ty
from collections import abc

from . import config, follow, gateway, host, wakes

HELLO: ty.Final = "lemonaid-source-plugin 1"
_LOOK = 0.5  # seconds between looks at the wake files
_INTEREST = 60.0  # seconds between touches of each followed conversation's interest file

_log = logging.getLogger("lemonaid_slack.serve")


class _Followed(ty.NamedTuple):
    sub: follow.Subscription
    follower: str
    stamp: int  # the wake file's when lemonaid last polled it


class _Server:
    def __init__(self, out: ty.BinaryIO) -> None:
        self._out = out
        self._write = threading.Lock()
        self._lock = threading.Lock()
        self.followed: dict[str, _Followed] = {}
        self.stopped = threading.Event()

    def send(self, data: bytes) -> None:
        with self._write:
            self._out.write(data)
            self._out.flush()

    def answer(self, lines: abc.Iterable[str]) -> None:
        body = "".join(f"{line}\n" for line in lines).encode()
        self.send(f"ok {len(body)}\n".encode() + body)

    def refuse(self, message: str) -> None:
        self.send(f"error {' '.join(message.split())}\n".encode())

    def notice(self, line: str) -> None:
        self.send(f"{line}\n".encode())

    def follow(self, key: str, followed: _Followed) -> None:
        with self._lock:
            self.followed[key] = followed

    def forget(self, key: str) -> None:
        with self._lock:
            self.followed.pop(key, None)

    def snapshot(self) -> dict[str, _Followed]:
        with self._lock:
            return dict(self.followed)


def _stamps(followed: abc.Mapping[str, _Followed]) -> dict[str, int]:
    return {
        key: wakes.stamp(f.sub.conversation.channel, f.sub.conversation.ts)
        for key, f in followed.items()
    }


def _watch(server: _Server) -> None:
    """Until the server stops: `ready` when a followed conversation's wake file changes, or for
    all of them when the socket comes up or goes down, since that changes how often each is
    fetched."""
    state = gateway.State()
    seen: dict[str, int] = {}
    up = wakes.gateway_up()
    touched_at = 0.0
    try:
        while not server.stopped.wait(_LOOK):
            followed = server.snapshot()
            gateway.tick(state, bool(followed), config.parse(host.table()))
            if time.monotonic() - touched_at >= _INTEREST:
                for f in followed.values():
                    wakes.follow(f.sub.conversation.channel, f.sub.conversation.ts, f.follower)
                touched_at = time.monotonic()
            stamps, now_up = _stamps(followed), wakes.gateway_up()
            for key, stamp in stamps.items():
                if stamp > max(seen.get(key, 0), followed[key].stamp) or now_up != up:
                    server.notice(f"ready {key}")
            seen, up = stamps, now_up
    finally:
        gateway.join(state)


def _poll(server: _Server, key: str, fields: abc.Sequence[tuple[str, str]], text: str) -> list[str]:
    args = [value for name, value in fields if name == "arg"]
    follower = next((value for name, value in fields if name == "follower"), "")
    done = any(name == "done" for name, _ in fields)
    sub = follow.parse(args)
    stamp = wakes.stamp(sub.conversation.channel, sub.conversation.ts)
    server.follow(key, _Followed(sub, follower, stamp))
    saved = json.loads(text) if text.strip() else None
    return follow.answer(sub, follower, saved, done, config.parse(host.table()))


def _handle(server: _Server, header: str, fields: list[tuple[str, str]], text: str) -> None:
    operation, _, key = header.partition(" ")
    try:
        if operation == "check":
            sub = follow.parse([value for name, value in fields if name == "arg"])
            server.answer(f"target {word}" for word in sub.conversation.target)
        elif operation == "poll":
            server.answer(_poll(server, key, fields, text))
        elif operation == "forget":
            server.forget(key)
            server.answer([])
        else:
            server.refuse(f"unknown request {operation!r}")
    except follow.Usage as error:
        server.refuse(str(error))
    except (OSError, ValueError, KeyError) as error:
        _log.exception("could not answer %s", header)
        server.refuse(f"{type(error).__name__}: {error}")


def _requests(
    stdin: ty.BinaryIO,
) -> abc.Iterator[tuple[str, list[tuple[str, str]], str]]:
    """(header, fields, text) of each request, until stdin closes, even partway through one."""
    while (header := stdin.readline()).endswith(b"\n"):
        fields: list[tuple[str, str]] = []
        while (line := stdin.readline()).endswith(b"\n"):
            name, _, value = line.decode().rstrip("\n").partition(" ")
            if name == "text":
                break

            fields.append((name, value))
        else:
            return

        if not value.isdigit() or len(text := stdin.read(int(value))) != int(value):
            return

        yield header.decode().rstrip("\n"), fields, text.decode()


def main(stdin: ty.BinaryIO | None = None, stdout: ty.BinaryIO | None = None) -> int:
    logging.basicConfig(
        stream=sys.stderr, level=logging.INFO, format="%(asctime)s %(name)s %(message)s"
    )
    server = _Server(stdout or sys.stdout.buffer)
    server.notice(HELLO)
    watcher = threading.Thread(target=_watch, args=(server,), name="slack-wakes", daemon=True)
    watcher.start()
    try:
        for header, fields, text in _requests(stdin or sys.stdin.buffer):
            _handle(server, header, fields, text)
    finally:
        server.stopped.set()
        watcher.join(timeout=10)
    return 0
