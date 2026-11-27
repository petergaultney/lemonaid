"""`lemonaid-relay-comments`: the Relay Comments document plugin.

It serves lemonaid's document plugin protocol on stdin and stdout until stdin closes;
see docs/doc-plugins.md.
"""

import sys
import typing as ty
from collections import abc

from . import threads

_HELLO: ty.Final = b"lemonaid-doc-plugin 1\n"


def _thread_lines(text: str, mine: abc.Set[str]) -> abc.Iterator[str]:
    for thread in threads.threads(text):
        author = threads.last_block(thread)[0]
        yield f"thread {threads.key(thread)}"
        yield f"last {' '.join(author.splitlines())}"
        if author not in mine:
            yield "waiting"
        yield f"gist {threads.gist(thread)}"
        yield from (f"text {line}" for line in threads.full_text(thread).split("\n"))


def answer(operation: str, text: str, names: abc.Set[str]) -> str:
    if operation == "body":
        return threads.body_without_threads(text)

    return "".join(f"{line}\n" for line in _thread_lines(text, names))


def _request(stdin: ty.BinaryIO) -> tuple[str, str, set[str]] | None:
    """(operation, text, names) of the next request, or None once stdin closes, even
    partway through a request."""
    first = stdin.readline()
    if not first.endswith(b"\n"):
        return None

    operation = first.decode().partition(" ")[0]
    names: set[str] = set()
    while (line := stdin.readline().decode()).startswith("name "):
        names.add(line[len("name ") :].rstrip("\n"))
    size = line.removeprefix("text ").strip()
    if not line.startswith("text ") or not size.isdigit():
        return None

    text = stdin.read(int(size))
    return (operation, text.decode(), names) if len(text) == int(size) else None


def serve(stdin: ty.BinaryIO, stdout: ty.BinaryIO) -> None:
    stdout.write(_HELLO)
    stdout.flush()
    while (request := _request(stdin)) is not None:
        operation, text, names = request
        if operation not in ("body", "threads"):
            stdout.write(f"error unknown operation {operation}\n".encode())
        else:
            result = answer(operation, text, names).encode()
            stdout.write(f"ok {len(result)}\n".encode() + result)
        stdout.flush()


def main() -> int:
    serve(sys.stdin.buffer, sys.stdout.buffer)
    return 0
