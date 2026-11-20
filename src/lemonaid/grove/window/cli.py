"""`lemonaid grove window`: the grove in a native window over the terminal (beta, macOS)."""

import argparse
import sys

from ...config import load_config
from . import control


def _cmd_run(_args: argparse.Namespace) -> None:
    if sys.platform != "darwin":
        sys.exit("The grove window runs on macOS only, for now")
    try:
        # Optional: pywebview and PyObjC come with the `web` extra, not with lemonaid itself.
        from . import app
    except ImportError as error:
        sys.exit(
            f"The grove window needs the web extra ({error.name} is missing): "
            "uv tool install 'lemonaid-inbox[web]'"
        )
    app.run(load_config())


def _cmd_send(args: argparse.Namespace) -> None:
    line = f"show {args.client}" if args.grove_window_command == "show" else "hide"
    try:
        control.send(line)
    except OSError:
        sys.exit("No grove window is running; `lemonaid grove window run` runs one")


def _cmd_binding(args: argparse.Namespace) -> None:
    print(control.binding(args.key))


def add_parsers(grove_subparsers: argparse._SubParsersAction) -> None:
    window = grove_subparsers.add_parser(
        "window", help="The grove in a native window a tmux key summons over the terminal (beta)"
    )
    commands = window.add_subparsers(dest="grove_window_command", required=True)
    commands.add_parser("run", help="Run the window here, hidden until summoned").set_defaults(
        func=_cmd_run
    )
    show = commands.add_parser("show", help="Summon the window, as the tmux key does")
    show.add_argument("--client", default="", help="The tmux client tty to switch on a jump")
    show.set_defaults(func=_cmd_send)
    commands.add_parser("hide", help="Hide the window").set_defaults(func=_cmd_send)
    binding = commands.add_parser("binding", help="Print the tmux.conf lines for the summon key")
    binding.add_argument(
        "--key", default="Space", help="The key after the tmux prefix (default Space)"
    )
    binding.set_defaults(func=_cmd_binding)
