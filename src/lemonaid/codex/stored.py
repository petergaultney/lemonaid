"""What Codex has stored about threads, read from an app-server.

A server outside a thread's own Codex process sees only what is stored: every thread shows
as not loaded, and no notification about it arrives. Live turn state comes from hooks.
"""

import typing as ty
from collections import abc

from . import app_server

# A `thread/turns/list` error with one of these means Codex has no conversation to resume:
# no such thread, a row whose rollout file is gone, or not a thread ID at all.
_GONE = ("thread not loaded", "missing source rollout", "invalid thread id")

_SOURCE_KINDS = [
    *("cli", "vscode", "exec", "appServer", "subAgent", "subAgentReview"),
    *("subAgentCompact", "subAgentThreadSpawn", "subAgentOther", "unknown"),
]

# Titles Codex gives its own approval-review threads, which say nothing about the lemon.
_GENERIC_NAMES = frozenset({"guardian review"})


class Thread(ty.NamedTuple):
    id: str
    cwd: str
    name: str
    model: str
    parent: str  # the thread a subagent or reviewer runs inside; "" for a top-level thread
    path: str  # Codex marks it unstable; for logs and humans, never for lookups
    updated_at: int  # Unix seconds
    archived: bool

    @property
    def resumable(self) -> bool:
        return not self.archived


def _thread(record: dict[str, ty.Any], archived: bool) -> Thread:
    name = (record.get("name") or "").strip()
    return Thread(
        id=record["id"],
        cwd=record.get("cwd") or "",
        name="" if name.lower() in _GENERIC_NAMES else name,
        model=record.get("model") or "",
        parent=record.get("parentThreadId") or "",
        path=record.get("path") or "",
        updated_at=int(record.get("updatedAt") or 0),
        archived=archived,
    )


def _archived(server: app_server.Server, timeout: float) -> set[str]:
    archived: set[str] = set()
    cursor = None
    while True:
        [reply] = server.ask(
            [
                (
                    "thread/list",
                    {
                        "archived": True,
                        "cursor": cursor,
                        "limit": 500,
                        "modelProviders": [],
                        "sourceKinds": _SOURCE_KINDS,
                    },
                )
            ],
            timeout,
        )
        if "error" in reply:
            raise app_server.NoAnswer(str(reply["error"]))

        archived |= {each["id"] for each in reply["result"]["data"]}
        if not (cursor := reply["result"].get("nextCursor")):
            return archived


def read(
    server: app_server.Server, threads: abc.Collection[str], timeout: float
) -> dict[str, Thread | None]:
    """Each thread Codex answers for: its record, or None when it has no conversation to
    resume. A thread Codex answered with an error it doesn't explain is left out."""
    archived = _archived(server, timeout)
    ordered = sorted(threads)
    replies = server.ask(
        [
            call
            for thread in ordered
            for call in (
                ("thread/read", {"threadId": thread, "includeTurns": False}),
                ("thread/turns/list", {"threadId": thread, "limit": 1}),
            )
        ],
        timeout,
    )
    answers: dict[str, Thread | None] = {}
    for thread, record, turns in zip(ordered, replies[::2], replies[1::2], strict=True):
        if "error" in turns:
            if any(gone in str(turns["error"].get("message", "")) for gone in _GONE):
                answers[thread] = None
        elif "error" not in record:
            answers[thread] = _thread(record["result"]["thread"], thread in archived)
    return answers


def latest_in(server: app_server.Server, cwd: str, timeout: float) -> Thread | None:
    """The most recently updated top-level interactive thread working in *cwd*."""
    [reply] = server.ask(
        [
            (
                "thread/list",
                {"cwd": [cwd], "limit": 1, "sortKey": "updated_at", "modelProviders": []},
            )
        ],
        timeout,
    )
    if "error" in reply:
        raise app_server.NoAnswer(str(reply["error"]))

    return next((_thread(each, False) for each in reply["result"]["data"]), None)


class Turn(ty.NamedTuple):
    completed: bool  # ended normally, rather than running, interrupted or failed
    said: tuple[str, ...]  # the assistant's messages, in order
    typed: tuple[str, ...]  # each user message that was a single piece of text, in order


def _turn(record: dict[str, ty.Any]) -> Turn:
    items = record.get("items") or []
    return Turn(
        completed=record.get("status") == "completed",
        said=tuple(i["text"] for i in items if i.get("type") == "agentMessage" and i.get("text")),
        typed=tuple(
            content[0].get("text", "")
            for i in items
            if i.get("type") == "userMessage"
            and len(content := i.get("content") or []) == 1
            and content[0].get("type") == "text"
        ),
    )


def latest_turns(server: app_server.Server, thread: str, count: int, timeout: float) -> list[Turn]:
    """The thread's newest *count* turns, newest first."""
    [reply] = server.ask(
        [("thread/turns/list", {"threadId": thread, "limit": count, "itemsView": "full"})], timeout
    )
    if "error" in reply:
        raise app_server.NoAnswer(str(reply["error"]))

    return [_turn(each) for each in reply["result"]["data"]]
