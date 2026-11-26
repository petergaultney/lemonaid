"""CLI commands for OpenClaw integration."""

import argparse
import os
from pathlib import Path

from ..front_end import chat
from ..inbox import db
from . import lemons, observe, sessions, sync
from .notify import dismiss_session, handle_dismiss, handle_notification, handle_register


def cmd_notify(args: argparse.Namespace) -> None:
    """Handle OpenClaw notification hook."""
    handle_notification(
        stdin_data=args.payload,
        session_id=args.session_id,
        agent_id=args.agent_id,
        session_path=args.session_path,
        cwd=args.cwd,
        name=args.name,
        message=args.message,
        notification_type=args.notification_type,
    )


def cmd_dismiss(args: argparse.Namespace) -> None:
    """Handle OpenClaw dismiss hook (mark notification as read)."""
    if args.session_id:
        dismiss_session(args.session_id)
    else:
        handle_dismiss()


def _register_key(key: str, claim: bool) -> int:
    try:
        found = sessions.listed(sessions.cli()).get(key)
    except sessions.Unavailable as error:
        print(f"not registered: {error}")
        return 1

    if found is None:
        print(f"not registered: OpenClaw stores no session {key!r}")
        return 1

    channel = sessions.channel(key)
    thread = os.environ.get("CODEX_THREAD_ID", "") if sessions.hosted_codex_home() else ""
    with db.connect() as conn:
        holder = lemons.by_thread(conn, thread) if thread else ""
        lent = holder not in ("", channel) and not claim  # the caller registers it for it
        kept = db.get_by_channel(conn, channel, unread_only=False)
        held = str(kept.metadata.get("codex_thread") or "") if kept else ""
        lemons.register(
            conn,
            found,
            held if lent else thread,
            sessions.hosted_codex_home(),
            os.getcwd(),
            chat.NAME,
            kept.name or "" if kept else "",
        )

    if lent:
        print(
            f"registered {channel}; your Codex thread stays {holder}'s"
            " (pass --claim if it is this session's)"
        )
    elif thread:
        print(f"registered {channel}")
    else:
        print(f"registered {channel}; run this inside that session so its own commands can find it")
    return 0


def cmd_register(args: argparse.Namespace) -> None:
    """Register an OpenClaw session with lemonaid: by session key, or the TUI's (captures TTY)."""
    if args.session_key:
        raise SystemExit(_register_key(args.session_key, args.claim))

    success = handle_register(session_id=args.session_id, cwd=args.cwd)
    if not success:
        raise SystemExit(1)


def cmd_sync(args: argparse.Namespace) -> None:
    try:
        added, archived = sync.refresh(sessions.cli(), args.days, sync.CHATS, chat.NAME)
    except sessions.Unavailable as error:
        raise SystemExit(f"not synced: {error}") from error

    print(f"{len(added)} added, {len(archived)} archived")


def cmd_observe(args: argparse.Namespace) -> None:
    cli = sessions.cli()
    if not Path(cli).exists():
        raise SystemExit(f"not observing: no openclaw executable at {cli}")

    observe.run(cli, args.days, args.every)


def setup_parser(subparsers: argparse._SubParsersAction) -> None:
    """Set up the openclaw subcommand."""
    openclaw_parser = subparsers.add_parser(
        "openclaw",
        help="OpenClaw integration",
    )
    openclaw_subparsers = openclaw_parser.add_subparsers(dest="openclaw_command")

    notify_parser = openclaw_subparsers.add_parser(
        "notify",
        help="Handle notification from OpenClaw hook (reads JSON from stdin)",
    )
    notify_parser.add_argument(
        "payload",
        nargs="?",
        help="JSON payload from OpenClaw hook (passed as a single argument)",
    )
    notify_parser.add_argument(
        "--session-id",
        "-s",
        help="Session ID to associate with the notification",
    )
    notify_parser.add_argument(
        "--agent-id",
        "-a",
        help="Agent ID (if known)",
    )
    notify_parser.add_argument(
        "--session-path",
        help="Path to OpenClaw session jsonl file",
    )
    notify_parser.add_argument(
        "--cwd",
        help="Working directory for the session",
    )
    notify_parser.add_argument(
        "--name",
        help="Display name for the session",
    )
    notify_parser.add_argument(
        "--message",
        help="Notification message override",
    )
    notify_parser.add_argument(
        "--notification-type",
        help="Notification/event type",
    )
    notify_parser.set_defaults(func=cmd_notify)

    dismiss_parser = openclaw_subparsers.add_parser(
        "dismiss",
        help="Mark session's notification as read (reads JSON from stdin)",
    )
    dismiss_parser.add_argument(
        "--session-id",
        "-s",
        help="Session ID to dismiss (if not provided, reads from stdin)",
    )
    dismiss_parser.set_defaults(func=cmd_dismiss)

    register_parser = openclaw_subparsers.add_parser(
        "register",
        help="Register session with lemonaid (run from TUI: !lemonaid openclaw register)",
    )
    register_parser.add_argument(
        "--session-id",
        "-s",
        help="Session ID to register (default: most recently modified session)",
    )
    register_parser.add_argument(
        "--session-key",
        help="register this gateway session as a lemon (run it inside the session; its key"
        " comes from the session_status tool)",
    )
    register_parser.add_argument(
        "--claim",
        action="store_true",
        help="with --session-key: bind this Codex thread to the session even when another lemon"
        " holds it, to repair a wrong registration",
    )
    register_parser.add_argument(
        "--cwd",
        help="Override cwd (default: use session's cwd from header)",
    )
    register_parser.set_defaults(func=cmd_register)

    sync_parser = openclaw_subparsers.add_parser(
        "sync",
        help="make each OpenClaw conversation active lately a lemon, and archive the ones that"
        " went quiet",
    )
    sync_parser.add_argument(
        "--days",
        type=float,
        default=sync.DAYS,
        help=f"how recent counts as active (default {sync.DAYS:g})",
    )
    sync_parser.set_defaults(func=cmd_sync)

    observe_parser = openclaw_subparsers.add_parser(
        "observe",
        help="keep running `sync` until stopped, for a service on the machine running the gateway",
    )
    observe_parser.add_argument(
        "--days",
        type=float,
        default=sync.DAYS,
        help=f"how recent counts as active (default {sync.DAYS:g})",
    )
    observe_parser.add_argument(
        "--every",
        type=float,
        default=observe.EVERY_SECONDS,
        help=f"seconds between syncs (default {observe.EVERY_SECONDS:g})",
    )
    observe_parser.set_defaults(func=cmd_observe)

    openclaw_parser.set_defaults(func=lambda a: openclaw_parser.print_help())
