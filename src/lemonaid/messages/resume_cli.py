"""`lemonaid lemon resume`: bring back one lemon because someone asked to.

Unlike `tell`'s autoresume, this resumes a lemon marked done or archived, and
ignores `[messages] autoresume`: the caller has decided. It shares the start
limit, so a lemon that keeps dying is refused here too.
"""

import argparse
import os
import sys
import typing as ty

from .. import brief
from ..config import load_config
from ..inbox import db
from . import autoresume, recipient, revive, store

_PROMPT = (
    "You were resumed by {who}: run `lemonaid inbox next --self` to read any messages, "
    "rearm the waiters your brief lists under ## Waiters, and carry on."
)
_NOTHING_TO_DO = frozenset({recipient.LISTENING, recipient.MID_TURN})


def _fail(message: str) -> ty.NoReturn:
    print(message, file=sys.stderr)
    raise SystemExit(1)


def _caller(explicit_channel: str) -> str:
    """The calling lemon's Lemon-ID, or its channel, or the user's name."""
    with db.connect() as conn:
        channel = brief.lemon.self_channel(
            conn, explicit_channel, os.environ.get("USER") or "unknown"
        )
        try:
            return brief.lemon.own_id(conn, channel)
        except (LookupError, ValueError, brief.store.ChangedUnderneath):
            return channel


def cmd_resume(args: argparse.Namespace) -> None:
    with db.connect() as conn:
        try:
            found = brief.lemon.attachment(conn, args.lemon)
            lemon_id = brief.identity.ensure(conn, found.path)
        except (LookupError, ValueError, brief.store.ChangedUnderneath) as error:
            _fail(str(error))
    if found.notification is None:
        _fail(f"{lemon_id} has no session recorded, so there is nothing to resume")

    row, inbox = found.notification, store.inbox_for_id(lemon_id)
    state = recipient.probe(found.channel, row, inbox)
    if state.state in _NOTHING_TO_DO:
        print(f"{lemon_id} is {state.state}: {state.detail}. Nothing to resume.")
        return

    if state.state not in (recipient.DEAD, recipient.DEAF):
        _fail(f"{lemon_id} is {state.state}: {state.detail}. lemonaid won't resume it.")

    who = _caller(args.channel or "")
    dead = state.state == recipient.DEAD
    outcome = revive.revive(row, inbox, dead, load_config(), args.prompt or _PROMPT.format(who=who))
    if outcome.kind == revive.STARTING:
        print(f"{lemon_id} is already being started.")
        return

    if outcome.kind == revive.CRASH_LOOPING:
        _fail(f"{lemon_id} was started too often recently; lemonaid won't start it again yet.")

    with db.connect() as conn:
        if outcome.kind == revive.FAILED:
            autoresume.post(conn, f"{who} asked to resume {lemon_id}, but: {outcome.why}")
            _fail(f"could not resume {lemon_id}: {outcome.why}")

        line = (
            f"{who} resumed {lemon_id} in a new window"
            if dead
            else f"{who} prompted {lemon_id}, which was idle with no inbox waiter"
        )
        autoresume.post(conn, line)
    print(line)


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "resume",
        help="Resume a lemon whose harness exited, or prompt one that is deaf",
        description="Resume a lemon in a new window of the terminal it ran in, or type a "
        "prompt into one that is idle with no inbox waiter. A lemon that is listening or "
        "mid-turn is left alone. This resumes lemons marked done or archived too, and "
        "counts against the same limit as tell's autoresume ([messages] autoresume_max).",
    )
    parser.add_argument("lemon", help="A Lemon-ID, channel, or attached brief name")
    parser.add_argument("--prompt", help="What to tell it on waking (default: read your inbox)")
    parser.add_argument("--channel", help="This lemon's channel, overriding self detection")
    parser.set_defaults(func=cmd_resume)
