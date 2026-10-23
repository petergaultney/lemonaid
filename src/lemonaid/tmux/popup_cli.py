"""`lemonaid tmux popup`: a fast popup over this client, for any app that provides one."""

import argparse

from ..config import load_config
from . import fast_popup, popup_binding, popup_resident


def _cmd_popup(args: argparse.Namespace) -> None:
    margin = load_config().tmux_session.popup_margin
    if args.binding:
        print(
            popup_binding.binding(args.name, args.binding, margin, args.title or f" {args.name} ")
        )
        return

    fast_popup.show(args.name, margin, args.title)


def _cmd_serve(args: argparse.Namespace) -> None:
    popup_resident.serve(args.name)


def add_parsers(subparsers: argparse._SubParsersAction) -> None:
    popup = subparsers.add_parser(
        "popup",
        help="Show an app in a popup over this client, starting its resident if needed",
        description="Show popup NAME, whose app is the module lemonaid.NAME.popup_app, such as "
        "`grove`. For a key that opens it without starting Python, add what "
        "`lemonaid tmux popup grove --binding Space` prints to your tmux.conf.",
    )
    popup.add_argument("name", help="The app, such as grove")
    popup.add_argument("--title", default="", help="The popup's title (default: the name)")
    popup.add_argument(
        "--binding", metavar="KEY", help="Print a tmux.conf binding of KEY to the popup, and exit"
    )
    popup.set_defaults(func=_cmd_popup)
    serve = subparsers.add_parser(
        "popup-serve", help="Run popup NAME's resident (started by `tmux popup`)"
    )
    serve.add_argument("name")
    serve.set_defaults(func=_cmd_serve)
