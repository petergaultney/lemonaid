"""CLI delivery of Markdown messages to briefs attached to lemon channels."""

import argparse
import os
import shlex
import sqlite3
import sys
from pathlib import Path

from .. import brief, lineage
from ..inbox import db
from ..log import get_logger
from ..watch import registry
from . import codex_delivery, recipient, service, store, waiter

_log = get_logger("messages.cli")
_INBOX_WATCH = ["lemonaid", "inbox", "watch", "--self"]


def _fail(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(1)


def _attachment(conn: sqlite3.Connection, channel: str) -> Path:
    brief.attached.claim_pending(conn)
    path = brief.attached.by_channel(conn, [channel]).get(channel)
    if path is None:
        _fail(f"No brief attached to {channel!r}; attach one before messaging")

    return path


def _linked(conn: sqlite3.Connection, args: argparse.Namespace) -> str:
    """The Lemon-ID of the caller's parent, or of its child `--child` names."""
    try:
        own = brief.lemon.own_id(conn, args.channel or "")
        if args.parent:
            parent = lineage.links.parent_of(conn, own)
            if not parent:
                _fail(f"{own} has no parent link; `lemonaid lemon parent --self --set <parent>`")

            return parent

        child = brief.lemon.lemon_id(conn, args.child)
    except (LookupError, ValueError, brief.store.ChangedUnderneath) as error:
        _fail(str(error))
        raise

    if lineage.links.parent_of(conn, child) != own:
        _fail(f"{child} is not a child of {own}")

    return child


def _recipient(conn: sqlite3.Connection, target: str) -> tuple[str, brief.attached.Attachment]:
    """(Lemon-ID, attachment) for *target*."""
    try:
        recipient = brief.lemon.attachment(conn, target)
        return brief.identity.ensure(conn, recipient.path), recipient
    except (LookupError, ValueError, brief.store.ChangedUnderneath) as error:
        _fail(str(error))
        raise


def cmd_tell(args: argparse.Namespace) -> None:
    linked = args.parent or args.child
    message = args.target if linked and args.message is None else args.message
    if (not linked and not args.target) or message is None:
        _fail(
            "Usage: lemonaid tell (<lemon-id-or-channel-or-brief> | --parent | --child <lemon>) <message>"
        )

    with db.connect() as conn:
        if linked:
            lemon_id = _linked(conn, args)
            try:
                found = brief.lemon.attachment(conn, lemon_id)
                channel, row = found.channel, found.notification
            except LookupError:
                channel, row = "", None  # not started yet; its messages wait in its inbox
        else:
            lemon_id, found = _recipient(conn, args.target)
            channel, row = found.channel, found.notification

        sender = brief.lemon.self_channel(
            conn, args.channel or "", os.environ.get("USER") or "unknown"
        )
        sender_brief = brief.attached.by_channel(conn, [sender]).get(sender)
        if sender_brief is not None:
            try:
                sender_id = brief.identity.ensure(conn, sender_brief)
                sender = f"{sender_id} ({sender}, {sender_brief.name})"
            except (ValueError, brief.store.ChangedUnderneath) as error:
                _fail(str(error))
    try:
        inbox = store.inbox_for_id(lemon_id)
        path = store.send(inbox, sys.stdin.read() if message == "-" else message, sender)
    except ValueError as error:
        _fail(str(error))

    if channel.startswith("codex:"):
        service.ensure_running()
    print(path)
    state = recipient.probe(channel, row, inbox)
    print(recipient.describe(lemon_id, state), file=sys.stderr)
    if state.state in recipient.UNREAD:
        raise SystemExit(1)


def own_lemon(explicit_channel: str) -> tuple[str, str]:
    """(channel, Lemon-ID) of the calling lemon; exits with a message if it has no brief."""
    with db.connect() as conn:
        try:
            channel = brief.lemon.self_channel(conn, explicit_channel)
        except LookupError as error:
            _fail(str(error))
        brief_path = _attachment(conn, channel)
        try:
            return channel, brief.identity.ensure(conn, brief_path)
        except (ValueError, brief.store.ChangedUnderneath) as error:
            _fail(str(error))
            raise


def _receive(args: argparse.Namespace, wait: bool) -> None:
    channel, lemon_id = own_lemon(args.channel or "")
    inbox = store.inbox_for_id(lemon_id)

    if wait:

        def still_attached() -> bool:
            with db.connect() as conn:
                current = brief.attached.by_channel(conn, [channel]).get(channel)
                if current is None or not current.is_file():
                    return False
                try:
                    now_id = brief.identity.from_path(current)
                except ValueError as error:
                    _log.warning("Invalid attached brief %s: %s", current, error)
                    return False

                if now_id != lemon_id and brief.lemon.current(conn, lemon_id) == now_id:
                    raise ValueError(f"Lemon-ID changed to {now_id}; rearm the waiter")

                return now_id == lemon_id

        codex_thread = args.codex_thread or codex_delivery.own_thread(channel)
        try:
            with (
                waiter.armed(inbox),
                registry.registered(
                    "inbox",
                    (lemon_id,),
                    channel,
                    shlex.join(getattr(args, "invocation", None) or _INBOX_WATCH),
                ),
            ):
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


_TELL_EPILOG = """\
The message is always queued. tell then says on stderr whether the recipient
will read it, and exits 1 when it won't (its harness isn't running, or it is
an idle Claude lemon with no inbox waiter). On exit 1, don't resend or wait
for a reply; follow the next step that line gives.
"""


def add_tell_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "tell",
        help="Send a Markdown message to a lemon's inbox",
        epilog=_TELL_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--parent", action="store_true", help="Send to this lemon's parent")
    group.add_argument(
        "--child",
        metavar="LEMON",
        help="Send to this lemon's child (a Lemon-ID, channel, or brief)",
    )
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
