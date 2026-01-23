"""CLI commands for tmux integration."""

import argparse
import sys
from pathlib import Path

from ..config import load_config
from . import go_back, swap_back_location
from .session import create_session


def cmd_back(args: argparse.Namespace) -> None:
    """Switch back to the previous tmux location."""
    if go_back():
        pass  # Success - switched back
    else:
        print("No previous location saved", file=sys.stderr)
        sys.exit(1)


def cmd_swap(args: argparse.Namespace) -> None:
    """Swap back location: save current, print target.

    Designed for tmux keybinding integration.
    Outputs "session|pane_id" on success, empty on failure.
    """
    target_session, target_pane = swap_back_location(args.session, args.pane_id)
    if target_session is not None and target_pane is not None:
        print(f"{target_session}|{target_pane}")


def cmd_new(args: argparse.Namespace) -> None:
    """Create a new tmux session from a template."""
    config = load_config()
    template_name = args.template

    windows = config.tmux_session.get_template(template_name)
    if windows is None:
        print(f"Template '{template_name}' not found in config", file=sys.stderr)
        print("Available templates:", file=sys.stderr)
        for name in config.tmux_session.templates:
            print(f"  - {name}", file=sys.stderr)
        if not config.tmux_session.templates:
            print("  (none configured)", file=sys.stderr)
        sys.exit(1)

    directory = Path(args.dir) if args.dir else Path.cwd()
    session_name = args.name or directory.name

    success = create_session(
        name=session_name,
        windows=windows,
        directory=directory,
        claude_rename=args.rename,
        attach=not args.detach,
    )
    if not success:
        sys.exit(1)


def setup_parser(subparsers: argparse._SubParsersAction) -> None:
    """Set up the tmux subcommand."""
    tmux_parser = subparsers.add_parser(
        "tmux",
        help="tmux integration commands",
    )
    tmux_subparsers = tmux_parser.add_subparsers(dest="tmux_command")

    # tmux back
    back_parser = tmux_subparsers.add_parser(
        "back",
        help="Switch back to previous location",
    )
    back_parser.set_defaults(func=cmd_back)

    # tmux swap - for keybinding integration
    swap_parser = tmux_subparsers.add_parser(
        "swap",
        help="Swap back location (for tmux keybinding integration)",
    )
    swap_parser.add_argument("session", help="Current session name")
    swap_parser.add_argument("pane_id", help="Current pane ID (e.g., %5)")
    swap_parser.set_defaults(func=cmd_swap)

    # tmux new - create session from template
    new_parser = tmux_subparsers.add_parser(
        "new",
        help="Create a new tmux session from a template",
    )
    new_parser.add_argument(
        "name",
        nargs="?",
        help="Session name (defaults to directory name)",
    )
    new_parser.add_argument(
        "--from",
        dest="template",
        default="default",
        help="Template name from config (default: 'default')",
    )
    new_parser.add_argument(
        "--dir",
        help="Working directory (default: current directory)",
    )
    new_parser.add_argument(
        "--rename",
        action="store_true",
        help="Send /rename to claude windows (usually not needed, lemonaid uses tmux session name)",
    )
    new_parser.add_argument(
        "-d",
        "--detach",
        action="store_true",
        help="Don't attach to the session after creation",
    )
    new_parser.set_defaults(func=cmd_new)

    tmux_parser.set_defaults(func=lambda a: tmux_parser.print_help())
