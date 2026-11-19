"""Which Codex threads can no longer be resumed, as Codex itself answers it.

One short-lived `codex app-server` on stdio answers a whole batch; it is never the shared
daemon. A thread it can't answer for is judged by looking for its rollout file.
"""

import contextlib
import json
import os
import select
import shutil
import subprocess
import time
import typing as ty
from collections import abc

from ..log import get_logger
from . import utils

_log = get_logger("codex.threads")
_TIMEOUT = 5.0

# Each start would otherwise sync the plugin catalog over the network into the Codex home.
_ARGV = (
    "app-server",
    *("--disable", "plugins", "--disable", "remote_plugin"),
    *("--disable", "plugin_discovery_prefetch"),
)

# A `thread/turns/list` error with one of these means Codex has no conversation to resume:
# no such thread, a row whose rollout file is gone, or not a thread ID at all.
_GONE = ("thread not loaded", "missing source rollout", "invalid thread id")

_SOURCE_KINDS = [
    *("cli", "vscode", "exec", "appServer", "subAgent", "subAgentReview"),
    *("subAgentCompact", "subAgentThreadSpawn", "subAgentOther", "unknown"),
]


class _NoAnswer(Exception):
    pass


def _line(message: dict[str, ty.Any]) -> bytes:
    return json.dumps(message).encode() + b"\n"


def _replies(
    proc: subprocess.Popen, outgoing: bytearray, deadline: float
) -> abc.Iterator[dict[str, ty.Any]]:
    """Codex's replies, while *outgoing* (which the caller may extend) is written to it.

    Writing and reading share *deadline*, so a Codex that stops reading its input can't
    block the caller on a full pipe.
    """
    assert proc.stdin and proc.stdout
    stdin, stdout = proc.stdin.fileno(), proc.stdout.fileno()
    os.set_blocking(stdin, False)
    buffer = b""
    while True:
        while b"\n" in buffer:
            line, _, buffer = buffer.partition(b"\n")
            if line.strip() and "id" in (message := json.loads(line)):
                yield message

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise _NoAnswer("timed out")

        readable, writable, _ = select.select([stdout], [stdin] if outgoing else [], [], remaining)
        if not readable and not writable:
            raise _NoAnswer("timed out")

        if writable:
            with contextlib.suppress(BlockingIOError):
                del outgoing[: os.write(stdin, outgoing)]
        if readable:
            chunk = os.read(stdout, 1 << 16)
            if not chunk:
                raise _NoAnswer(f"exited with {proc.poll()}")

            buffer += chunk


def _archived_page(cursor: str | None) -> dict[str, ty.Any]:
    return {
        "archived": True,
        "cursor": cursor,
        "limit": 500,
        "modelProviders": [],
        "sourceKinds": _SOURCE_KINDS,
    }


def _answer(reply: dict[str, ty.Any]) -> bool | None:
    if "error" not in reply:
        return False

    message = str(reply["error"].get("message", ""))
    return True if any(gone in message for gone in _GONE) else None


def _converse(proc: subprocess.Popen, threads: list[str]) -> dict[str, bool | None]:
    """Each thread's answer: True gone, False resumable, None when Codex's error is unknown."""
    outgoing = bytearray(
        b"".join(
            [
                _line(
                    {
                        "id": 0,
                        "method": "initialize",
                        "params": {"clientInfo": {"name": "lemonaid", "version": "0"}},
                    }
                ),
                _line({"method": "initialized"}),
                _line({"id": -1, "method": "thread/list", "params": _archived_page(None)}),
                *(
                    _line(
                        {
                            "id": number,
                            "method": "thread/turns/list",
                            "params": {"threadId": thread, "limit": 1},
                        }
                    )
                    for number, thread in enumerate(threads, 1)
                ),
            ]
        )
    )
    archived: set[str] = set()
    listing = True
    answers: dict[str, bool | None] = {}
    for reply in _replies(proc, outgoing, time.monotonic() + _TIMEOUT):
        number = reply["id"]
        if number <= 0 and "error" in reply:
            raise _NoAnswer(reply["error"].get("message", "error"))

        if number < 0:
            archived |= {each["id"] for each in reply["result"]["data"]}
            if cursor := reply["result"].get("nextCursor"):
                outgoing += _line(
                    {"id": number - 1, "method": "thread/list", "params": _archived_page(cursor)}
                )
            else:
                listing = False
        elif number > 0:
            answers[threads[number - 1]] = _answer(reply)
        if not listing and len(answers) == len(threads):
            break

    return {thread: True if thread in archived else answer for thread, answer in answers.items()}


def _ask(threads: list[str]) -> dict[str, bool | None]:
    """Codex's answers, or none at all when it can't be asked."""
    codex = shutil.which("codex")
    if codex is None:
        return {}

    try:
        proc = subprocess.Popen(
            [codex, *_ARGV],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0,
        )
    except OSError as error:
        _log.warning("could not start codex app-server: %s", error)
        return {}

    try:
        return _converse(proc, threads)
    except (_NoAnswer, OSError, ValueError, KeyError, TypeError) as error:
        _log.warning("codex app-server did not answer for %d threads: %s", len(threads), error)
        return {}
    finally:
        proc.kill()
        proc.wait()


def gone(threads: abc.Iterable[str]) -> set[str]:
    """The *threads* Codex can't resume: unknown, archived, or whose rollout is gone.

    A blank thread is gone. A thread Codex gives no clear answer for is gone when no
    rollout file for it is in the sessions directory.
    """
    threads = set(threads)
    asked = sorted(thread for thread in threads if thread)
    answers = _ask(asked) if asked else {}
    return {
        thread
        for thread in threads
        if not thread
        or (
            answers[thread]
            if answers.get(thread) is not None
            else utils.find_session_path(thread, compressed=True) is None
        )
    }
