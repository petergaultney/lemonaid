"""CLI commands for WezTerm integration."""

import argparse
import sys

from . import go_back, swap_back_location


def cmd_back(args: argparse.Namespace) -> None:
    """Switch back to the previous WezTerm location."""
    if go_back():
        pass  # Success - switched back
    else:
        print("No previous location saved", file=sys.stderr)
        sys.exit(1)


def cmd_swap(args: argparse.Namespace) -> None:
    """Swap back location: save current, print target.

    Designed for WezTerm Lua integration to minimize Lua code.
    Outputs "workspace|pane_id" on success, empty on failure.
    """
    target_ws, target_pane = swap_back_location(args.workspace, args.pane_id)
    if target_ws is not None and target_pane is not None:
        print(f"{target_ws}|{target_pane}")


def setup_parser(subparsers: argparse._SubParsersAction) -> None:
    """Set up the wezterm subcommand."""
    wezterm_parser = subparsers.add_parser(
        "wezterm",
        help="WezTerm integration commands",
    )
    wezterm_subparsers = wezterm_parser.add_subparsers(dest="wezterm_command")

    # wezterm back
    back_parser = wezterm_subparsers.add_parser(
        "back",
        help="Switch back to previous location",
    )
    back_parser.set_defaults(func=cmd_back)

    # wezterm swap - for Lua integration
    swap_parser = wezterm_subparsers.add_parser(
        "swap",
        help="Swap back location (for WezTerm Lua integration)",
    )
    swap_parser.add_argument("workspace", help="Current workspace name")
    swap_parser.add_argument("pane_id", type=int, help="Current pane ID")
    swap_parser.set_defaults(func=cmd_swap)

    wezterm_parser.set_defaults(func=lambda a: wezterm_parser.print_help())
