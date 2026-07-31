"""CLI commands for places - directories you work in, and their sessions."""

import argparse
import dataclasses
import json
import sys
from pathlib import Path

from ..config import Config, PlaceRoot, load_config
from . import lifecycle, ownership, toss_cli


def root_or_exit(config: Config, directory: str | Path) -> PlaceRoot:
    root = config.places.root_for(directory)
    if root is None:
        print(
            f"No places root configured for {directory}.\n"
            "Add one to ~/.config/lemonaid/config.toml under [[places.roots]].",
            file=sys.stderr,
        )
        sys.exit(1)

    return root


def cmd_open(args: argparse.Namespace) -> None:
    """Get a session for a key, acquiring its directory if it doesn't exist yet."""
    config = load_config()
    root = root_or_exit(config, args.root or Path.cwd())

    directory, error = lifecycle.open_key(args.key, config, root, attach=not args.detach)

    if args.json:
        print(
            json.dumps(
                {
                    "key": args.key,
                    "dir": str(directory) if directory else None,
                    "root": str(root.path),
                    "error": error,
                }
            )
        )
    elif error:
        print(error, file=sys.stderr)

    if error:
        sys.exit(1)


def cmd_list(args: argparse.Namespace) -> None:
    """List the directories every configured root reports."""
    config = load_config()
    if not config.places.roots:
        print("No [[places.roots]] configured", file=sys.stderr)
        sys.exit(1)

    known = ownership.managed_places(config)
    occupied = {
        place.directory: session
        for session in ownership.pane_paths()
        for place in ownership.places_of(session, config, known)
    }

    # The key is included so a caller can act on a listed directory without
    # having to re-derive one; these came from the roots' own listings, so they
    # are known to be managed.
    listing = [
        {
            "root": str(place.root.path),
            "dir": str(place.directory),
            "key": place.key,
            "session": occupied.get(place.directory, ""),
        }
        for place in known
    ]

    if args.json:
        print(json.dumps(listing))
        return

    for entry in listing:
        print(entry["dir"])


def cmd_hooks(args: argparse.Namespace) -> None:
    """Show the commands configured for managing directories.

    This is how a person or a lemon finds out how directories are acquired and
    released here, without that convention having to be written down somewhere
    that can drift from the config.
    """
    config = load_config()
    roots = [root_or_exit(config, args.root)] if args.root else config.places.roots

    resolved = [{**dataclasses.asdict(root), "path": str(root.path)} for root in roots]

    if args.json:
        print(json.dumps(resolved))
        return

    if not resolved:
        print("No [[places.roots]] configured", file=sys.stderr)
        sys.exit(1)

    for root in resolved:
        print(root.pop("path"))
        for name, command in root.items():
            print(f"  {name:8} {command or '-'}")


def setup_parser(subparsers: argparse._SubParsersAction) -> None:
    """Set up the place subcommand."""
    place_parser = subparsers.add_parser(
        "place",
        help="Directories you work in, and their tmux sessions",
        description="A place is a directory you work in. lemonaid knows about "
        "directories and terminals - what acquires and releases a directory is a "
        "shell command declared per repo root, so run `place hooks --json` rather "
        "than assuming a tool. `toss` operates on a tmux session and every place it "
        "occupies. Full guide for automated callers: `lemonaid for-lemons`.",
    )
    place_subparsers = place_parser.add_subparsers(dest="place_command")

    # "new" is kept as a hidden alias: this verb creates only when it has to, so
    # naming it after creation misdescribes the common case of reopening.
    open_parser = place_subparsers.add_parser(
        "open",
        aliases=["new"],
        help="Get a session for a key, acquiring its directory if needed",
        description="Acquires the directory only if it doesn't exist, and switches "
        "to its session only if there isn't one. Neither case is an error, so this "
        "is always safe to run without checking first.",
    )
    open_parser.add_argument("key", help="What the root's tool names directories by")
    open_parser.add_argument(
        "--root", help="Root to acquire under (default: the one containing cwd)"
    )
    open_parser.add_argument(
        "-d", "--detach", action="store_true", help="Don't switch to the session"
    )
    open_parser.add_argument("--json", action="store_true", help="Print the result as JSON")
    open_parser.set_defaults(func=cmd_open)

    list_parser = place_subparsers.add_parser("list", help="List directories under every root")
    list_parser.add_argument("--json", action="store_true", help="Print the listing as JSON")
    list_parser.set_defaults(func=cmd_list)

    toss_cli.add_parser(place_subparsers)

    hooks_parser = place_subparsers.add_parser(
        "hooks",
        help="Show how directories are acquired and released here",
    )
    hooks_parser.add_argument("--root", help="Only show this root")
    hooks_parser.add_argument("--json", action="store_true", help="Print the hooks as JSON")
    hooks_parser.set_defaults(func=cmd_hooks)

    place_parser.set_defaults(func=lambda a: place_parser.print_help())
