"""CLI commands for macOS notification integration."""

import argparse
import sys


def _check_macos_deps() -> bool:
    """Check if macOS dependencies are installed."""
    try:
        import ApplicationServices  # noqa: F401
        import Quartz  # noqa: F401

        return True
    except ImportError:
        return False


def _require_macos_deps() -> None:
    """Exit with helpful message if macOS deps not installed."""
    if not _check_macos_deps():
        print("macOS notification support requires additional dependencies.", file=sys.stderr)
        print("Install with: pip install lemonaid[macos]", file=sys.stderr)
        print("         or: uv pip install lemonaid[macos]", file=sys.stderr)
        sys.exit(1)


def cmd_notify(args: argparse.Namespace) -> None:
    """Handle a notification from the macOS watcher daemon."""
    from .notify import handle_notification

    handle_notification(
        app_bundle_id=args.app,
        title=args.title,
        body=args.body,
        workspace=args.workspace or None,
        ax_id=args.ax_id or None,
    )


def cmd_install_watcher(args: argparse.Namespace) -> None:
    """Install and start the macOS notification watcher daemon."""
    _require_macos_deps()
    from .launchd import install_watcher

    install_watcher(start=not args.no_start)


def cmd_uninstall_watcher(args: argparse.Namespace) -> None:
    """Stop and uninstall the macOS notification watcher daemon."""
    from .launchd import uninstall_watcher

    uninstall_watcher()


def cmd_watcher_status(args: argparse.Namespace) -> None:
    """Check status of the macOS notification watcher daemon."""
    from .launchd import watcher_status

    watcher_status()


def cmd_watcher_logs(args: argparse.Namespace) -> None:
    """Show recent logs from the macOS notification watcher daemon."""
    from .launchd import watcher_logs

    watcher_logs(lines=args.lines, follow=args.follow)


def setup_parser(subparsers: argparse._SubParsersAction) -> None:
    """Set up the macos subcommand."""
    macos_parser = subparsers.add_parser(
        "macos",
        help="macOS Notification Center integration",
    )
    macos_subparsers = macos_parser.add_subparsers(dest="macos_command")

    # macos notify - called by the watcher daemon
    notify_parser = macos_subparsers.add_parser(
        "notify",
        help="Handle notification from watcher daemon (internal use)",
    )
    notify_parser.add_argument(
        "--app",
        required=True,
        help="App bundle ID (e.g., com.tinyspeck.slackmacgap)",
    )
    notify_parser.add_argument(
        "--title",
        required=True,
        help="Notification title",
    )
    notify_parser.add_argument(
        "--body",
        default="",
        help="Notification body text",
    )
    notify_parser.add_argument(
        "--workspace",
        default="",
        help="Slack workspace name (for multi-workspace deep linking)",
    )
    notify_parser.add_argument(
        "--ax-id",
        default="",
        help="macOS accessibility identifier (for deduplication)",
    )
    notify_parser.set_defaults(func=cmd_notify)

    # macos install-watcher
    install_parser = macos_subparsers.add_parser(
        "install-watcher",
        help="Install the notification watcher daemon (LaunchAgent)",
    )
    install_parser.add_argument(
        "--no-start",
        action="store_true",
        help="Install but don't start the watcher",
    )
    install_parser.set_defaults(func=cmd_install_watcher)

    # macos uninstall-watcher
    uninstall_parser = macos_subparsers.add_parser(
        "uninstall-watcher",
        help="Stop and uninstall the notification watcher daemon",
    )
    uninstall_parser.set_defaults(func=cmd_uninstall_watcher)

    # macos status
    status_parser = macos_subparsers.add_parser(
        "status",
        help="Check watcher daemon status",
    )
    status_parser.set_defaults(func=cmd_watcher_status)

    # macos logs
    logs_parser = macos_subparsers.add_parser(
        "logs",
        help="Show watcher daemon logs",
    )
    logs_parser.add_argument(
        "-n",
        "--lines",
        type=int,
        default=20,
        help="Number of lines to show (default: 20)",
    )
    logs_parser.add_argument(
        "-f",
        "--follow",
        action="store_true",
        help="Follow log output (like tail -f)",
    )
    logs_parser.set_defaults(func=cmd_watcher_logs)

    macos_parser.set_defaults(func=lambda a: macos_parser.print_help())
