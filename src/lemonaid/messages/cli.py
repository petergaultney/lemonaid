"""CLI delivery of Markdown messages to briefs attached to lemon channels."""

import argparse
import os
import sqlite3
import sys
from pathlib import Path

from .. import brief
from ..inbox import db, self_session
from ..inbox.channel import channel_id
from ..log import get_logger
from . import codex_delivery, service, store, waiter

_log = get_logger("messages.cli")


def _fail(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(1)


def _attachment(conn: sqlite3.Connection, channel: str) -> Path:
    brief.attached.claim_pending(conn)
    path = brief.attached.by_channel(conn, [channel]).get(channel)
    if path is None:
        _fail(f"No brief attached to {channel!r}; attach one before messaging")

    return path


def _target(conn: sqlite3.Connection, target: str) -> brief.attached.Attachment:
    brief.attached.claim_pending(conn)
    all_briefs = brief.attached.everything(conn)
    found = [entry for entry in all_briefs if entry.channel == target and entry.channel]
    if not found and brief.identity.valid(target):
        for entry in all_briefs:
            if not entry.channel or not entry.path.is_file():
                continue
            try:
                if brief.identity.from_path(entry.path) == target:
                    found.append(entry)
            except ValueError as error:
                _log.warning("Skipping invalid brief %s: %s", entry.path, error)

    if not found:
        found = [
            entry
            for entry in all_briefs
            if entry.channel and (entry.path.stem == target or entry.path.name == target)
        ]
    if len(found) != 1:
        _fail(f"Expected one attached lemon for {target!r}; found {len(found)}")

    return found[0]


def _self_channel(conn: sqlite3.Connection, explicit: str = "", fallback: str = "") -> str:
    channel = explicit or os.environ.get("LEMONAID_CHANNEL", "")
    if channel:
        return channel

    if session_id := os.environ.get("CLAUDE_CODE_SESSION_ID"):
        return channel_id("claude", session_id)

    if session_id := os.environ.get("CODEX_THREAD_ID"):
        return channel_id("codex", session_id)

    if pane_id := os.environ.get("TMUX_PANE"):
        where = self_session.pane_location(pane_id)
        if where is None:
            if fallback:
                return fallback

            _fail(f"Could not ask tmux where pane {pane_id} is")

        channel, error = self_session.resolve(conn, where)
        if error:
            if fallback:
                return fallback

            _fail(error)

        return channel

    if fallback:
        return fallback

    _fail("Cannot identify this lemon; set LEMONAID_CHANNEL or use a tmux pane")


def cmd_tell(args: argparse.Namespace) -> None:
    if args.parent or args.child:
        _fail(
            "--parent and --child require lemon parent links (planned in item 3); use a stable ID, channel, or brief name"
        )

    if not args.target or args.message is None:
        _fail("Usage: lemonaid tell <lemon-id-or-channel-or-brief> <message>")

    with db.connect() as conn:
        recipient = _target(conn, args.target)
        try:
            lemon_id = brief.identity.ensure(conn, recipient.path)
        except (ValueError, brief.store.ChangedUnderneath) as error:
            _fail(str(error))

        sender = _self_channel(conn, args.channel or "", os.environ.get("USER") or "unknown")
        sender_brief = brief.attached.by_channel(conn, [sender]).get(sender)
        if sender_brief is not None:
            try:
                sender_id = brief.identity.ensure(conn, sender_brief)
                sender = f"{sender_id} ({sender}, {sender_brief.name})"
            except (ValueError, brief.store.ChangedUnderneath) as error:
                _fail(str(error))
    try:
        inbox = store.inbox_for_id(lemon_id)
        path = store.send(inbox, sys.stdin.read() if args.message == "-" else args.message, sender)
    except ValueError as error:
        _fail(str(error))

    if recipient.channel.startswith("codex:"):
        service.ensure_running()
    print(path)


def _receive(args: argparse.Namespace, wait: bool) -> None:
    with db.connect() as conn:
        channel = _self_channel(conn, args.channel or "")
        brief_path = _attachment(conn, channel)
        try:
            lemon_id = brief.identity.ensure(conn, brief_path)
        except (ValueError, brief.store.ChangedUnderneath) as error:
            _fail(str(error))

    inbox = store.inbox_for_id(lemon_id)

    if wait:

        def still_attached() -> bool:
            with db.connect() as conn:
                current = brief.attached.by_channel(conn, [channel]).get(channel)
                if current is None or not current.is_file():
                    return False
                try:
                    return brief.identity.from_path(current) == lemon_id
                except ValueError as error:
                    _log.warning("Invalid attached brief %s: %s", current, error)
                    return False

        codex_thread = args.codex_thread or codex_delivery.own_thread(channel)
        try:
            with waiter.armed(inbox):
                result = store.watch_next(
                    inbox,
                    still_attached,
                    args.timeout,
                    find=(
                        (lambda inbox: codex_delivery.deliver_next(inbox, codex_thread))
                        if codex_thread
                        else store.take_next
                    ),
                )
        except (ValueError, TimeoutError, RuntimeError, waiter.AlreadyArmed) as error:
            _fail(str(error))

        if codex_thread:
            print(result[1], end="")
            return
    else:
        result = store.take_next(inbox)

    if result is None:
        raise SystemExit(1)

    path, message = result
    try:
        print(message, end="" if message.endswith("\n") else "\n")
        sys.stdout.flush()
    except (OSError, UnicodeError):
        store.restore(path)
        raise


def cmd_next(args: argparse.Namespace) -> None:
    _receive(args, wait=False)


def cmd_watch(args: argparse.Namespace) -> None:
    _receive(args, wait=True)


def add_tell_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("tell", help="Send a Markdown message to a lemon's inbox")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--parent", action="store_true", help="Parent link (requires item 3)")
    group.add_argument("--child", metavar="NAME", help="Child link (requires item 3)")
    parser.add_argument("--channel", help="Sender channel, overriding self detection")
    parser.add_argument(
        "target", nargs="?", help="Stable lemon ID, channel, or attached brief name"
    )
    parser.add_argument("message", nargs="?", help="Message text")
    parser.set_defaults(func=cmd_tell)


def add_inbox_parsers(subparsers: argparse._SubParsersAction) -> None:
    for name, command, help_text in (
        ("next", cmd_next, "Print and handle the next message, if any"),
        ("watch", cmd_watch, "Wait for one message, print it, and handle it"),
    ):
        parser = subparsers.add_parser(name, help=help_text)
        parser.add_argument("--self", dest="self_target", action="store_true", required=True)
        parser.add_argument("--channel", help="This lemon's channel, overriding self detection")
        if name == "watch":
            parser.add_argument("--timeout", type=float, help="Maximum seconds to wait")
            parser.add_argument(
                "--codex-thread",
                metavar="THREAD",
                help="Queue the message into this Codex thread (default: $CODEX_THREAD_ID when watching that thread)",
            )
        parser.set_defaults(func=command, codex_thread="")
