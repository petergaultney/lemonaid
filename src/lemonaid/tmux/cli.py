"""CLI commands for tmux integration."""

import argparse
import json
import sys
from pathlib import Path

from ..config import load_config
from ..inbox import db, doctor
from . import restart as tmux_restart
from . import restore as tmux_restore
from . import scratch
from .navigation import go_back, swap_back_location
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

    if args.restart:
        result = tmux_restart.restart_scratch()
    elif args.flip:
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

    if args.verbose or args.restart:
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


def cmd_doctor(args: argparse.Namespace) -> None:
    """Report what restore knows, before you need it to know it."""
    for line in doctor.report():
        print(line)

    if args.unknown:
        panes = doctor.unknown_panes()
        print("\nRunning, but not in the inbox")
        for pane in panes:
            print(f"  {pane.session}:{pane.window:<4} {pane.tty}")
        if not panes:
            print("  (none)")


def cmd_adopt(args: argparse.Namespace) -> None:
    """Put running panes the inbox does not know about into the inbox."""
    plans = doctor.plan_adoption()
    if not plans:
        print("nothing to adopt: every running agent pane is already in the inbox")
        return

    certain = [p for p in plans if not p.contested]
    guessed = [p for p in plans if p.contested]

    for plan in certain:
        print(f"  {plan.pane.session}:{plan.pane.window:<4} {plan.session_id}  {plan.cwd}")

    for plan in guessed:
        print(f"  {plan.pane.session}:{plan.pane.window:<4} {plan.session_id}  {plan.cwd}  (guess)")

    if guessed:
        print(
            f"\n{len(guessed)} marked (guess): several panes share that directory and nothing"
            "\non disk says which conversation belonged to which pane."
        )

    if args.dry_run:
        print(f"\nwould adopt {len(plans)}; nothing written")
        return

    chosen = certain if args.skip_guesses else plans
    print(f"\nadopted {doctor.adopt(chosen)}")


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
        "--restart",
        action="store_true",
        help="Restart the lma process in the scratch pane, keeping the pane where it is",
    )
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

    adopt_parser = tmux_subparsers.add_parser(
        "adopt",
        help="Put running agent panes into the inbox, so restore knows about them",
        description="Finds agent panes with no inbox row and records them, matching "
        "each to its conversation by working directory and most recent activity.\n\n"
        "A running pane is the one case where missing facts can still be recovered: "
        "it is there to be asked. Sessions started before the SessionStart hook was "
        "installed are exactly this, and would otherwise stay invisible until each "
        "happened to notify.\n\n"
        "Where several panes share a directory the match is a guess and is marked as "
        "one; --skip-guesses adopts only the certain ones.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    adopt_parser.add_argument(
        "-n", "--dry-run", action="store_true", help="Show what would be adopted, and write nothing"
    )
    adopt_parser.add_argument(
        "--skip-guesses", action="store_true", help="Adopt only panes whose match is unambiguous"
    )
    adopt_parser.set_defaults(func=cmd_adopt)

    doctor_parser = tmux_subparsers.add_parser(
        "doctor",
        help="Report what could be restored after a crash, and what could not",
        description="What lemonaid currently knows about your running sessions.\n\n"
        "Restore depends on facts recorded long before you need them - a window "
        "location, a session id, a hook that either fired or did not. This says "
        "whether they are there while you can still do something about it.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    doctor_parser.add_argument(
        "--unknown", action="store_true", help="List running panes the inbox does not know about"
    )
    doctor_parser.set_defaults(func=cmd_doctor)

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
