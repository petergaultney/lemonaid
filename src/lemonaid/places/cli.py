"""CLI commands for places - directories you work in, and their sessions."""

import argparse
import dataclasses
import json
import sys
from pathlib import Path

from .. import brief
from ..config import Config, PlaceRoot, load_config
from ..inbox import db
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


def _attach_brief(
    path: Path,
    key: str,
    directory: Path,
    in_root: bool,
    config: Config,
    harness: str,
    after_id: int,
) -> str | None:
    """Wait on the new session's harness window for its lemon. Returns an error, or None."""
    session = lifecycle.session_for(key, directory, in_root)
    if not session:
        return f"Opened, but could not tell which session is {directory}'s to attach {path}"

    with db.connect() as conn:
        brief.attached.attach_pending(
            conn, session, lifecycle.harness_window(config, harness), path, after_id
        )
    return None


def cmd_open(args: argparse.Namespace) -> None:
    """Get a session for a key, acquiring its directory if it doesn't exist yet."""
    config = load_config()
    brief_path = brief.store.resolve(args.brief) if args.brief else None
    if brief_path and (error := brief.store.outside_error(brief_path)):
        print(error, file=sys.stderr)
        sys.exit(1)

    if brief_path and not brief_path.is_file():
        print(f"No brief at {brief_path}", file=sys.stderr)
        sys.exit(1)

    # Taken before the session exists, so a lemon that starts quickly still counts.
    after_id = 0
    if brief_path:
        with db.connect() as conn:
            after_id = brief.attached.newest_id(conn)

    # Naming a root asks for its vocabulary explicitly, so an unusable one is an
    # error rather than something to read another way.
    root = (
        root_or_exit(config, args.root)
        if args.root
        else config.places.namespaced_root_for(Path.cwd())
    )

    if root is None:
        directory = Path.cwd()
        error = lifecycle.open_session(
            args.key,
            directory,
            config,
            attach=not args.detach,
            harness=args.harness,
            prompt=args.prompt,
        )
    else:
        directory, error = lifecycle.open_key(
            args.key,
            config,
            root,
            attach=not args.detach,
            harness=args.harness,
            prompt=args.prompt,
        )

    if brief_path and directory and not error:
        error = _attach_brief(
            brief_path, args.key, directory, root is not None, config, args.harness, after_id
        )

    if args.json:
        print(
            json.dumps(
                {
                    "key": args.key,
                    "dir": str(directory) if directory else None,
                    "root": str(root.path) if root else None,
                    "brief": str(brief_path) if brief_path else None,
                    "error": error,
                }
            )
        )
    elif error:
        print(error, file=sys.stderr)

    if error:
        sys.exit(1)


def cmd_acquire(args: argparse.Namespace) -> None:
    """Get the directory for a key, creating it if needed, without a session."""
    config = load_config()
    root = (
        root_or_exit(config, args.root)
        if args.root
        else config.places.namespaced_root_for(Path.cwd())
    )

    if root is None:
        print(
            f"No root with a key vocabulary covers {Path.cwd()}, so there is no "
            "directory to acquire. Run `place hooks --json` to see the configured roots.",
            file=sys.stderr,
        )
        sys.exit(1)

    directory, error = lifecycle.acquire_key(args.key, root)

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
    elif directory:
        print(directory)

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
        "is always safe to run without checking first.\n\n"
        "If you only need the directory, use `place acquire` instead. Nothing is "
        "recorded here that later cleanup depends on - a directory acquired either "
        "way is reported by `list` and released by `toss` - so a session is the only "
        "thing this adds.\n\n"
        "Run from a directory no configured root manages the names of, there is no "
        "key to resolve, so the name is simply a session opened in the current "
        "directory - nothing is acquired. Passing --root asks for that root's "
        "vocabulary explicitly and fails if it has none.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    open_parser.add_argument(
        "key", help="What the root's tool names directories by, or a session name outside one"
    )
    open_parser.add_argument(
        "--root", help="Root to acquire under (default: the one containing cwd)"
    )
    open_parser.add_argument(
        "--harness",
        default="default",
        metavar="NAME",
        help="Use [tmux-session.templates].NAME (default: default)",
    )
    open_parser.add_argument(
        "--prompt",
        default="",
        help="Pass an initial prompt to the configured harness window",
    )
    open_parser.add_argument(
        "--brief",
        default="",
        metavar="FILE",
        help="Attach this brief (a path, or a name in ~/.brief-lemons/) to the first "
        "lemon that starts in the session's harness window",
    )
    open_parser.add_argument(
        "-d",
        "--detach",
        action="store_true",
        help="Create the session without switching to it (still creates one)",
    )
    open_parser.add_argument("--json", action="store_true", help="Print the result as JSON")
    open_parser.set_defaults(func=cmd_open)

    acquire_parser = place_subparsers.add_parser(
        "acquire",
        help="Get a key's directory, creating it if needed, with no tmux session",
        description="Prints the directory for a key, running the root's `create` "
        "hook first if it doesn't exist yet. No tmux session is created.\n\n"
        "This is what an automated caller wants: it has its own session, will never "
        "attach to a tmux one, and `place open` would leave an unused session "
        "behind. Nothing is recorded either way - ownership is derived from tmux "
        "when asked - so a directory acquired here is reported by `list` and "
        "released by `toss` exactly like one that had a session.\n\n"
        "Idempotent: an existing directory is printed rather than re-created, and "
        "that is not an error, so there is no need to check first.",
        epilog="Examples:\n"
        '  place acquire feat/thing --json   # {"key", "dir", "root", "error"}\n'
        "  cd $(place acquire feat/thing)    # the directory, one line",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    acquire_parser.add_argument("key", help="What the root's tool names directories by")
    acquire_parser.add_argument(
        "--root", help="Root to acquire under (default: the one containing cwd)"
    )
    acquire_parser.add_argument("--json", action="store_true", help="Print the result as JSON")
    acquire_parser.set_defaults(func=cmd_acquire)

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
