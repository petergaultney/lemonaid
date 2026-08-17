"""CLI commands for tmux integration."""

import argparse
import json
import sys
from pathlib import Path

from ..config import load_config
from ..inbox import db
from . import restore as tmux_restore
from .navigation import go_back, swap_back_location
from . import scratch
from .scratch import ensure_scratch, set_follow, toggle_scratch
from .session import auto_session_name, create_session


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


def cmd_scratch(args: argparse.Namespace) -> None:
    """Toggle the scratch lma pane."""
    config = load_config()
    # Config is the default; the state file is where you left it, and an explicit
    # flag beats both.
    position = args.position or scratch.current_position(config.tmux_session.scratch_position)
    if args.flip:
        position = scratch.flip_position(config.tmux_session.scratch_position)

    # The saved size beats config: it is what the follow hook will use, and a
    # pane shown at one width and rejoined at another is a visible jump.
    size = (
        args.size
        or scratch.saved_size(position)
        or (
            config.tmux_session.scratch_width
            if position == "left"
            else config.tmux_session.scratch_height
        )
    )

    if args.flip:
        result = scratch.move_scratch(size=size, position=position)
    elif args.follow is not None:
        result = set_follow(size=size, position=position, enable=args.follow)
    elif args.position:
        result = scratch.move_scratch(size=size, position=position)
    elif args.ensure:
        result = ensure_scratch(size=size, position=position)
    else:
        result = toggle_scratch(
            size=size,
            position=position,
            follow_default=config.tmux_session.follow_scratch,
        )

    if args.verbose:
        print(result)


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
    session_name = args.session_name or auto_session_name(directory)

    success = create_session(
        name=session_name,
        windows=windows,
        directory=directory,
        claude_rename=args.rename,
        attach=not args.detach,
    )
    if not success:
        sys.exit(1)


def cmd_restore(args: argparse.Namespace) -> None:
    """Rebuild the tmux layout the inbox describes."""
    config = load_config()
    with db.connect() as conn:
        plans = tmux_restore.plan_restore(db.get_active(conn, switch_source="tmux"), config)

    if args.dry_run:
        if args.json:
            print(json.dumps(tmux_restore.as_json(plans)))
            return

        for line in tmux_restore.describe(plans):
            print(line)
        return

    restored, skipped = tmux_restore.restore(plans)

    if args.json:
        print(json.dumps({"restored": restored, "skipped": skipped}))
        return

    for name in restored:
        print(f"restored {name}")

    for name in skipped:
        print(f"{name} is already running; left alone", file=sys.stderr)

    if not plans:
        print(tmux_restore.describe(plans)[0], file=sys.stderr)


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
    swap_parser.add_argument("pane_id", help="Current pane ID (e.g., %%5)")
    swap_parser.set_defaults(func=cmd_swap)

    # tmux scratch - toggle scratch pane
    scratch_parser = tmux_subparsers.add_parser(
        "scratch",
        help="Toggle the scratch lma pane (show/hide)",
        description="Toggle a persistent lma pane that stays running. "
        "First invocation creates it, subsequent invocations show/hide it.",
    )
    scratch_parser.add_argument(
        "--size",
        default=None,
        help="Size of the scratch pane: rows if it sits on top, columns if on the left"
        " (default: from config)",
    )
    scratch_parser.add_argument(
        "--position",
        choices=("top", "left"),
        default=None,
        help="Move the scratch pane to this edge, and keep it there",
    )
    scratch_parser.add_argument(
        "--flip",
        action="store_true",
        help="Move the scratch pane to the other edge (top <-> left)",
    )
    scratch_parser.add_argument(
        "--height", dest="size", default=None, help=argparse.SUPPRESS
    )  # pre-0.16 spelling of --size, kept so existing .tmux.conf bindings work
    scratch_parser.add_argument(
        "--ensure",
        action="store_true",
        help="Show the scratch pane if hidden, but never hide it (for hooks)",
    )
    follow_group = scratch_parser.add_mutually_exclusive_group()
    follow_group.add_argument(
        "--follow",
        action="store_const",
        const=True,
        default=None,
        help="Keep the scratch pane visible across all windows (installs tmux hooks)",
    )
    follow_group.add_argument(
        "--unfollow",
        dest="follow",
        action="store_const",
        const=False,
        help="Stop following across windows (removes tmux hooks)",
    )
    scratch_parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print action taken (created/shown/hidden)",
    )
    scratch_parser.set_defaults(func=cmd_scratch)

    # tmux new - create session from template
    new_parser = tmux_subparsers.add_parser(
        "new",
        help="Create a new tmux session from a template",
    )
    new_parser.add_argument(
        "-s",
        dest="session_name",
        help="Session name (default: auto-derived from directory path)",
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

    restore_parser = tmux_subparsers.add_parser(
        "restore",
        help="Rebuild tmux sessions for the active inbox after a crash",
        description="Recreates the tmux sessions the inbox says its active lemons "
        "were running in, resuming each one in the window it occupied.\n\n"
        "Windows keep their recorded index, so a window lemonaid knows nothing "
        "about - an editor, a shell - comes back as an empty gap rather than "
        "shifting the others down. Restored sessions are detached: putting a "
        "day's work back means starting many processes at once, and fighting over "
        "the client while that happens helps nobody.\n\n"
        "A session that is already running is left alone, so this is safe to run "
        "after rebuilding some of them by hand. Sessions recorded before lemonaid "
        "began storing their location cannot be placed and are skipped; "
        "--dry-run shows exactly what would happen.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    restore_parser.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="Print the layout that would be rebuilt, and start nothing",
    )
    restore_parser.add_argument("--json", action="store_true", help="Print the result as JSON")
    restore_parser.set_defaults(func=cmd_restore)

    tmux_parser.set_defaults(func=lambda a: tmux_parser.print_help())
