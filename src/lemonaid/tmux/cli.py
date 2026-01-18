"""CLI commands for tmux integration."""

import argparse
import sys

from . import go_back, swap_back_location


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

    tmux_parser.set_defaults(func=lambda a: tmux_parser.print_help())
