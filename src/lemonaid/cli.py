"""CLI entry point for lemonaid.

Lemonaid is a toolkit for working with lemons (LLMs). Current features:
- inbox: Attention management / notification inbox for tracking which lemons need you
"""

import argparse

from .claude import cli as claude_cli
from .config import ensure_config_exists, get_config_path
from .inbox import cli as inbox_cli
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


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="lemonaid",
        description="Toolkit for working with lemons (LLMs)",
    )
    subparsers = parser.add_subparsers(dest="command")

    inbox_cli.setup_parser(subparsers)
    claude_cli.setup_parser(subparsers)
    tmux_cli.setup_parser(subparsers)
    wezterm_cli.setup_parser(subparsers)
    setup_config_parser(subparsers)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
    elif hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


def inbox_main() -> None:
    """Direct entry point for `lma` alias - goes straight to inbox TUI."""
    from .inbox.tui import LemonaidApp

    app = LemonaidApp()
    app.run()


if __name__ == "__main__":
    main()
