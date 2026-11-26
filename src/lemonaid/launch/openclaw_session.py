"""`lemon start` beside an OpenClaw session: a new, ordinary session of the caller's agent.

It is a root session, with no `parentSessionKey`, so OpenClaw neither announces its runs to
the caller nor tells the caller about its messages. Its only parent is lemonaid's, which
hears of its brief's status.

The lemon is registered before its first message, which asks it to register again from
inside: that binds the Codex thread its `--self` commands carry, which exists only once
a turn runs.
"""

import argparse
import shlex
import sqlite3
import sys
import time
import uuid
from pathlib import Path

from .. import brief
from ..front_end import chat
from ..inbox import db
from ..openclaw import gateway, lemons, sessions, sync
from ..watch import children_waiter, openclaw_scout
from . import handoff

_CALL_TIMEOUT_SECONDS = 60


def _unsupported(args: argparse.Namespace) -> list[str]:
    return [
        flag
        for flag, given in (
            ("--harness", args.harness != "default"),
            ("--preset", args.preset),
            ("--shape", args.shape),
            ("--docs", args.docs),
            ("--lemon-arg", args.lemon_arg),
            ("-- <harness arguments>", getattr(args, "lemon_args", ())),
            ("--dry-run", args.dry_run),
        )
        if given
    ]


def register_line(key: str) -> str:
    register = f"lemonaid openclaw register --session-key {shlex.quote(key)}"
    return (
        f"Your OpenClaw session key is {key}. Before any other lemonaid command, run"
        f" `{register}` so lemonaid can find you."
    )


def first_message(key: str, prompt: str) -> str:
    return " ".join(part for part in (register_line(key), prompt) if part)


def new_session(conn: sqlite3.Connection, agent: sync.Agent, title: str) -> sessions.Session:
    """Create a root session of *agent* and register it as a lemon. Raises OSError."""
    key = f"agent:{agent.id}:dashboard:{uuid.uuid4()}"
    created = gateway.call(
        sessions.cli(),
        "sessions.create",
        {"key": key, "agentId": agent.id, **({"displayName": title} if title else {})},
        _CALL_TIMEOUT_SECONDS,
    )
    found = sessions.Session(
        key=key,
        session_id=str(created.get("sessionId") or ""),
        agent_id=agent.id,
        kind="direct",
        status="",
        updated_ms=int(time.time() * 1000),
        total_tokens=0,
        context_tokens=0,
    )
    lemons.register(conn, found, "", None, agent.workspace, chat.NAME, title or agent.name)
    return found


def _scouted(brief_path: Path, channel: str, cwd: str) -> bool:
    """Start the lemon's push scout, as a Claude lemon's SessionStart hook does, so its mail
    and watch events reach it as turns."""
    with db.connect() as conn:
        lemon_id = brief.identity.ensure(conn, brief_path)
    return openclaw_scout.ensure(channel, lemon_id, cwd)


def beside(args: argparse.Namespace) -> tuple[dict, str]:
    """A new session of the caller's agent, as a lemon shown through its chat front end."""
    if flags := _unsupported(args):
        return {}, (
            f"{', '.join(flags)}: an OpenClaw session runs its agent's own model and docs,"
            " so there is no harness line to choose or show"
        )

    agent_id = sessions.hosted_agent()
    try:
        agent = sync.agents(sessions.cli()).get(agent_id)
    except sessions.Unavailable as error:
        return {}, str(error)

    if agent is None:
        return {}, f"OpenClaw lists no agent {agent_id!r}"

    given, error = handoff.prepare(args.brief, args.parent, args.name, tuple(args.group))
    if error:
        return {}, error

    title = handoff.session_title(given)
    try:
        with db.connect() as conn:
            found = new_session(conn, agent, title)
    except OSError as error:
        return {}, f"sessions.create failed: {error}"

    key = found.key
    if warning := handoff.complete_on(given, sessions.channel(key)):
        print(f"Warning: {warning}", file=sys.stderr)
    if given.brief and not _scouted(given.brief, sessions.channel(key), agent.workspace):
        print(f"Warning: no push scout runs for {key}; its mail waits", file=sys.stderr)
    if given.link:
        print(children_waiter.reminder(), file=sys.stderr)

    result = {
        "front_end": chat.NAME,
        "where": f"OpenClaw session {key}",
        "session_key": key,
        "channel": sessions.channel(key),
        "dir": agent.workspace,
        "harness": "openclaw",
        "brief": str(given.brief) if given.brief else None,
        "lemon_id": given.link[0] if given.link else None,
        "parent": given.link[1] if given.link else None,
        "groups": list(given.groups),
        "name": given.name or None,
    }
    sent = chat.send(key, first_message(key, handoff.first_prompt(given, args.prompt)))
    return result, f"the session started, but its first message wasn't sent: {sent}" if sent else ""
