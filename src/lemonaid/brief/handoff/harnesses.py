"""What a handoff asks of each harness, so the core never branches on a harness's name.

The core - request, readiness, launch in a pane or by hand, accept, transfer - is the same
for every harness. Each entry supplies only what differs: how the accepting lemon names its
own channel, whether the outgoing lemon's final reply can carry the ready marker, where its
user's typed handoff phrases are read, and, for a harness with no terminal to launch in,
how to start the receiver itself. A new harness adds an entry here.
"""

import dataclasses
import os
import sqlite3
from collections import abc
from pathlib import Path

from ...inbox.channel import channel_id, full_channel_id
from . import claude, codex, openclaw

Record = abc.Callable[[str], object]  # records one message its user typed


@dataclasses.dataclass(frozen=True)
class Harness:
    name: str
    own_channel: abc.Callable[[sqlite3.Connection], str]
    """The channel of the lemon running this process, from its environment; "" if unknown."""
    reply_has_marker: abc.Callable[[sqlite3.Connection, sqlite3.Row], bool] = lambda conn, row: (
        False
    )
    """Whether the outgoing lemon's last completed reply ends with the ready marker."""
    typed: abc.Callable[[sqlite3.Connection, str, Record], None] = lambda conn, channel, record: (
        None
    )
    """Pass each recent message its user typed in a channel to the recorder. Where a harness's
    hooks report typed prompts as they come, this reads nothing."""
    request_note: abc.Callable[[str, Path], str] = lambda channel, brief: ""
    """What the outgoing lemon, on a channel with a brief, must be told besides the handoff
    request; "" or a sentence ending with a space."""
    answers_when_archived: bool = False
    """An archived lemon of this harness still takes a turn when sent one, so a handoff restores
    it to the inbox and asks it as it would a live one."""
    start: (
        abc.Callable[[sqlite3.Connection, sqlite3.Row, abc.Callable[[str], None]], None] | None
    ) = None
    """Start the receiver once the sender is ready, handing its channel to the callback before
    it is prompted. None: the core replaces the sender in its pane, or prints a command."""


def _env_channel(
    backend: str, variable: str, full: bool
) -> abc.Callable[[sqlite3.Connection], str]:
    def own(conn: sqlite3.Connection) -> str:
        session_id = os.environ.get(variable, "")
        if not session_id:
            return ""

        return full_channel_id(backend, session_id) if full else channel_id(backend, session_id)

    return own


HARNESSES: dict[str, Harness] = {
    each.name: each
    for each in (
        Harness(
            "claude",
            _env_channel("claude", "CLAUDE_CODE_SESSION_ID", full=False),
            claude.has_ready_marker,
        ),
        Harness(
            "codex",
            _env_channel("codex", "CODEX_THREAD_ID", full=True),
            codex.has_ready_marker,
            codex.typed,
            request_note=lambda channel, brief: (
                "If Codex blocks writing this brief or running `lemonaid brief check`, "
                "retry those operations with escalated permissions before reporting ready. "
            ),
        ),
        Harness(
            "openclaw",
            openclaw.own_channel,
            start=openclaw.start,
            request_note=openclaw.request_note,
            answers_when_archived=True,
        ),
    )
}

_UNKNOWN = Harness("", lambda conn: "")


def named(name: str) -> Harness:
    return HARNESSES.get(name, _UNKNOWN)


def of(channel: str) -> Harness:
    return named(channel.split(":", 1)[0])
