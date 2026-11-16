"""`lemonaid lemon resume`: bring back one lemon because someone asked to (see `bring_back`)."""

import argparse
import os
import sys
import typing as ty

from .. import brief
from ..config import load_config
from ..inbox import db
from . import bring_back

_PROMPT = (
    "You were resumed by {who}: run `lemonaid mailbox next --self` to read any messages, "
    "rearm the waiters your brief lists under ## Waiters, and carry on."
)


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
    who = _caller(args.channel or "")
    try:
        resumed = bring_back.resume(
            args.lemon, args.recreate, who, args.prompt or _PROMPT.format(who=who), load_config()
        )
    except bring_back.Refused as refused:
        _fail(str(refused))

    for line in resumed.lines:
        print(line)
    if resumed.warning:
        print(f"Warning: {resumed.warning}", file=sys.stderr)


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "resume",
        help="Resume a lemon whose harness exited, or prompt one that is deaf",
        description="Resume a lemon in a new window of the terminal it ran in, or type a "
        "prompt into one that is idle with no mailbox waiter. A lemon that is listening or "
        "mid-turn is left alone, and so is one lost with its terminal while a restore runs. "
        "This resumes lemons marked done or archived too, and "
        "counts against the same limit as tell's autoresume ([messages] autoresume_max). "
        "Without --recreate, a lemon whose tmux session is gone can't be resumed, and one "
        "whose directory is gone is resumed in the nearest directory that still exists.",
    )
    parser.add_argument("lemon", help="A Lemon-ID, channel, or attached brief name")
    parser.add_argument("--prompt", help="What to tell it on waking (default: read your mailbox)")
    parser.add_argument("--channel", help="This lemon's channel, overriding self detection")
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Put back what a toss took first: revive its archived brief and attach it to its "
        "session, recreate its place's directory through the root's hooks (refusing when "
        "the places log doesn't say which place it was), and recreate its tmux session "
        "under the recorded name and server",
    )
    parser.set_defaults(func=cmd_resume)
