"""CLI commands for Claude Code integration."""

import argparse

from .notify import dismiss_session, handle_dismiss, handle_notification
from .patcher import apply_patch, check_status, find_binary, restore_backup


def cmd_notify(args: argparse.Namespace) -> None:
    """Handle Claude Code notification hook."""
    handle_notification()


def cmd_dismiss(args: argparse.Namespace) -> None:
    """Handle Claude Code dismiss hook (mark notification as read)."""
    if args.session_id:
        # Direct session_id provided (e.g., from another hook that already parsed stdin)
        dismiss_session(args.session_id)
    else:
        # Read from stdin (original behavior)
        handle_dismiss()


def cmd_patch(args: argparse.Namespace) -> None:
    """Patch Claude Code to reduce notification delay."""
    binary = find_binary()
    if not binary:
        print("Could not find Claude Code binary")
        return

    print(f"Binary: {binary}")
    status = check_status(binary)
    print(f"Status: {status}")

    if status == "patched" and not args.force:
        print("Already patched. Use --force to re-apply.")
        return

    if status == "unknown":
        print("Pattern not found - binary format may have changed")
        return

    count = apply_patch(binary, backup=True)
    if count > 0:
        print(f"Patched {count} location(s). Notification delay: 6s -> 0.5s")
        print("Note: You'll need to re-patch after Claude Code updates.")
    else:
        print("No patterns found to patch")


def cmd_patch_status(args: argparse.Namespace) -> None:
    """Check Claude Code patch status."""
    binary = find_binary()
    if not binary:
        print("Could not find Claude Code binary")
        return

    print(f"Binary: {binary}")
    status = check_status(binary)
    print(f"Status: {status}")


def cmd_patch_restore(args: argparse.Namespace) -> None:
    """Restore Claude Code from backup."""
    binary = find_binary()
    if not binary:
        print("Could not find Claude Code binary")
        return

    if restore_backup(binary):
        print(f"Restored {binary} from backup")
    else:
        print("No backup found")


def setup_parser(subparsers: argparse._SubParsersAction) -> None:
    """Set up the claude subcommand."""
    claude_parser = subparsers.add_parser(
        "claude",
        help="Claude Code integration",
    )
    claude_subparsers = claude_parser.add_subparsers(dest="claude_command")

    # claude notify
    notify_parser = claude_subparsers.add_parser(
        "notify",
        help="Handle notification from Claude Code hook (reads JSON from stdin)",
    )
    notify_parser.set_defaults(func=cmd_notify)

    # claude dismiss
    dismiss_parser = claude_subparsers.add_parser(
        "dismiss",
        help="Mark session's notification as read (reads JSON from stdin)",
    )
    dismiss_parser.add_argument(
        "--session-id",
        "-s",
        help="Session ID to dismiss (if not provided, reads from stdin)",
    )
    dismiss_parser.set_defaults(func=cmd_dismiss)

    # claude patch
    patch_parser = claude_subparsers.add_parser(
        "patch",
        help="Patch Claude Code to reduce notification delay (6s -> 0.5s)",
    )
    patch_parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Re-apply patch even if already patched",
    )
    patch_parser.set_defaults(func=cmd_patch)

    # claude patch-status
    patch_status_parser = claude_subparsers.add_parser(
        "patch-status",
        help="Check if Claude Code is patched",
    )
    patch_status_parser.set_defaults(func=cmd_patch_status)

    # claude patch-restore
    patch_restore_parser = claude_subparsers.add_parser(
        "patch-restore",
        help="Restore Claude Code from backup",
    )
    patch_restore_parser.set_defaults(func=cmd_patch_restore)

    claude_parser.set_defaults(func=lambda a: claude_parser.print_help())
