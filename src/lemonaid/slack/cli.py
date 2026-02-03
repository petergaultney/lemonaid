"""CLI commands for Slack integration."""

from __future__ import annotations

import argparse

from .mappings import get_mappings_path, load_mappings


def cmd_show_mappings(args: argparse.Namespace) -> None:
    """Display current Slack ID mappings."""
    mappings = load_mappings(args.path)

    if not mappings:
        print("No mappings found.")
        print(f"Mappings file: {get_mappings_path()}")
        print()
        print("See docs/macos.md for instructions on generating mappings")
        print("from Slack's browser IndexedDB.")
        return

    workspace_filter = args.workspace
    if workspace_filter:
        if workspace_filter not in mappings:
            print(f"Workspace '{workspace_filter}' not found in mappings")
            print(f"Available: {', '.join(mappings.keys())}")
            return
        mappings = {workspace_filter: mappings[workspace_filter]}

    for ws_name, ws_data in mappings.items():
        print(f"\n{ws_name}")
        print(f"  Team ID: {ws_data.get('team_id', 'unknown')}")

        channels = ws_data.get("channels", {})
        print(f"  Channels ({len(channels)}):")
        for name in sorted(channels.keys())[:10]:
            print(f"    {name}")
        if len(channels) > 10:
            print(f"    ... and {len(channels) - 10} more")

        dms = ws_data.get("dms", {})
        print(f"  DMs ({len(dms)}):")
        for name in sorted(dms.keys())[:10]:
            print(f"    {name}")
        if len(dms) > 10:
            print(f"    ... and {len(dms) - 10} more")


def cmd_path(args: argparse.Namespace) -> None:
    """Print the mappings file path."""
    print(get_mappings_path())


def setup_parser(subparsers: argparse._SubParsersAction) -> None:
    """Set up the slack subcommand."""
    slack_parser = subparsers.add_parser(
        "slack",
        help="Slack integration (view ID mappings for deep linking)",
    )
    slack_subparsers = slack_parser.add_subparsers(dest="slack_command")

    # slack show-mappings
    show_parser = slack_subparsers.add_parser(
        "show-mappings",
        help="Display current Slack ID mappings",
    )
    show_parser.add_argument(
        "-p",
        "--path",
        help="Path to mappings file",
    )
    show_parser.add_argument(
        "-w",
        "--workspace",
        help="Show only this workspace",
    )
    show_parser.set_defaults(func=cmd_show_mappings)

    # slack path
    path_parser = slack_subparsers.add_parser(
        "path",
        help="Print the mappings file path",
    )
    path_parser.set_defaults(func=cmd_path)

    slack_parser.set_defaults(func=lambda a: slack_parser.print_help())
