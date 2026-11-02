"""A checker's serve mode: one long-running process answering framed requests.

A request is `request<TAB>ID<TAB>OPERATION`, then the operation's input exactly as a file
would hold it, then `end<TAB>ID`. The checker answers each request with `response<TAB>ID`,
its output, and `end<TAB>ID`, or with a single `failed<TAB>ID<TAB>REASON` line. Answers
may come in any order, so a checker can work on several requests at once. Fields are
escaped as in every other record.
"""

import typing as ty
from collections import abc

from . import protocol


class Frame(ty.NamedTuple):
    kind: str  # request, response or failed
    request_id: str
    detail: str  # a request's operation, or why it failed
    body: str


def _body(text: str) -> str:
    return text if not text or text.endswith("\n") else text + "\n"


def request(request_id: str, operation: str, text: str) -> str:
    return (
        protocol.line("request", request_id, operation)
        + _body(text)
        + protocol.line("end", request_id)
    )


def response(request_id: str, text: str) -> str:
    return protocol.line("response", request_id) + _body(text) + protocol.line("end", request_id)


def failed(request_id: str, reason: str) -> str:
    return protocol.line("failed", request_id, reason)


def _opening(fields: list[str]) -> tuple[str, str, str] | None:
    if fields[0] == "request" and len(fields) == 3:
        return "request", fields[1], fields[2]

    if fields[0] == "response" and len(fields) == 2:
        return "response", fields[1], ""

    return None


def frames(lines: abc.Iterable[str]) -> abc.Iterator[Frame]:
    """Each frame in *lines* as it completes; raises ProtocolError on a line outside a
    frame, or a frame the input ends inside."""
    opened: tuple[str, str, str] | None = None
    body: list[str] = []
    for raw in lines:
        fields = [protocol.unescape(f) for f in raw.rstrip("\n").split("\t")]
        if opened is None:
            if fields[0] == "failed" and len(fields) == 3:
                yield Frame("failed", fields[1], fields[2], "")
            elif (opened := _opening(fields)) is None:
                raise protocol.ProtocolError(f"line outside a frame: {raw!r}")

            body = []
        elif fields == ["end", opened[1]]:
            yield Frame(*opened, "".join(body))
            opened = None
        else:
            body.append(raw if raw.endswith("\n") else raw + "\n")
    if opened is not None:
        raise protocol.ProtocolError(f"{opened[0]} {opened[1]} has no end")


def serve(respond: abc.Callable[[str, str], str], lines: abc.Iterable[str], out: ty.TextIO) -> None:
    """Answer each request in *lines* until they end. *respond* takes an operation and its
    input and returns the output; a ValueError from it answers that request as failed."""
    for frame in frames(lines):
        try:
            answer = response(frame.request_id, respond(frame.detail, frame.body))
        except ValueError as error:
            answer = failed(frame.request_id, str(error) or type(error).__name__)
        out.write(answer)
        out.flush()
