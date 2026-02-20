"""CLI entry point for lemonaid.

Lemonaid is a toolkit for working with lemons (LLMs). Current features:
- inbox: Attention management / notification inbox for tracking which lemons need you
"""

import argparse

from .claude import cli as claude_cli
from .codex import cli as codex_cli
from .config import ensure_config_exists, get_config_path
from .inbox import cli as inbox_cli
from .inbox import db as inbox_db
from .openclaw import cli as openclaw_cli
from .opencode import cli as opencode_cli
from .tmux import cli as tmux_cli
from .wezterm import cli as wezterm_cli


# Config commands (kept here since config isn't a package)
def cmd_config_init(args: argparse.Namespace) -> None:
    """Initialize config file with defaults."""
    config_path = ensure_config_exists()
    print(f"Config file at: {config_path}")


def cmd_config_path(args: argparse.Namespace) -> None:
    """Print config file path."""
    print(get_config_path())


def cmd_config_show(args: argparse.Namespace) -> None:
    """Show current config."""
    config_path = get_config_path()
    if config_path.exists():
        print(config_path.read_text())
    else:
        print(f"No config file at {config_path}")
        print("Run 'lemonaid config init' to create one.")


def cmd_mark_read(args: argparse.Namespace) -> None:
    """Mark notifications as read by TTY."""
    with inbox_db.connect() as conn:
        count = inbox_db.mark_read_by_tty(conn, args.tty)
    if count > 0:
        print(f"Marked {count} notification(s) as read")
    else:
        print("No matching notifications")


def setup_config_parser(subparsers: argparse._SubParsersAction) -> None:
    """Set up the config subcommand."""
    config_parser = subparsers.add_parser(
        "config",
        help="Manage lemonaid configuration",
    )
    config_subparsers = config_parser.add_subparsers(dest="config_command")

    # config init
    init_parser = config_subparsers.add_parser("init", help="Create default config file")
    init_parser.set_defaults(func=cmd_config_init)

    # config path
    path_parser = config_subparsers.add_parser("path", help="Print config file path")
    path_parser.set_defaults(func=cmd_config_path)

    # config show
    show_parser = config_subparsers.add_parser("show", help="Show current config")
    show_parser.set_defaults(func=cmd_config_show)

    config_parser.set_defaults(func=cmd_config_show, config_command=None)


def setup_mark_read_parser(subparsers: argparse._SubParsersAction) -> None:
    """Set up the mark-read command for tmux integration."""
    parser = subparsers.add_parser(
        "mark-read",
        help="Mark notifications as read by TTY (for tmux keybindings)",
        description="Mark all unread notifications from a specific TTY as read.",
    )
    parser.add_argument(
        "--tty",
        required=True,
        help="The TTY device path (e.g., /dev/ttys005)",
    )
    parser.set_defaults(func=cmd_mark_read)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="lemonaid",
        description="Toolkit for working with lemons (LLMs)",
    )
    subparsers = parser.add_subparsers(dest="command")

    inbox_cli.setup_parser(subparsers)
    claude_cli.setup_parser(subparsers)
    codex_cli.setup_parser(subparsers)
    openclaw_cli.setup_parser(subparsers)
    opencode_cli.setup_parser(subparsers)
    tmux_cli.setup_parser(subparsers)
    wezterm_cli.setup_parser(subparsers)
    setup_config_parser(subparsers)
    setup_mark_read_parser(subparsers)

    args = parser.parse_args()

    try:
        if args.command is None:
            parser.print_help()
        elif hasattr(args, "func"):
            args.func(args)
        else:
            parser.print_help()
    except Exception:
        import sys
        import time
        import traceback

        # Log to file since Claude Code may hide stderr
        with open("/tmp/lemonaid-errors.log", "a") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {' '.join(sys.argv)}\n")
            f.write(traceback.format_exc())
            f.write("\n")
        raise


def inbox_main() -> None:
    """Direct entry point for `lma` alias - goes straight to inbox TUI."""
    import argparse
    import os

    from .inbox.tui import LemonaidApp, set_terminal_title

    parser = argparse.ArgumentParser(prog="lma", description="Lemonaid attention inbox")
    parser.add_argument(
        "--scratch",
        action="store_true",
        help="Run as a scratch pane: auto-hide after selecting a notification",
    )
    args = parser.parse_args()

    set_terminal_title("lma")
    app = LemonaidApp(scratch_mode=args.scratch)
    app.run()

    # If the user chose to resume a session, exec it in this terminal
    if app._exec_on_exit:
        cwd, argv = app._exec_on_exit
        os.chdir(cwd)
        os.execvp(argv[0], argv)


if __name__ == "__main__":
    main()
