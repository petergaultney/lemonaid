"""`brief lemon add|set|rm`: keep the list of lemons a lemon watches besides its children."""

import argparse

from . import command, lemon_table, store, verbs_cli


def _to(value: str) -> str:
    if value != lemon_table.NEEDS and value not in store.STATES:
        raise argparse.ArgumentTypeError(
            f"{value!r} is not one of {', '.join((*store.STATES, lemon_table.NEEDS))}"
        )

    return value


def _cmd(args: argparse.Namespace) -> None:
    path, error = command.own_brief(args)
    if path:
        error = verbs_cli.edit(
            path,
            lambda text: (
                lemon_table.add(text, args.lemon, args.purpose, args.to)
                if args.verb == "add"
                else lemon_table.set_row(text, args.lemon, args.purpose, args.to or None)
                if args.verb == "set"
                else lemon_table.remove(text, args.lemon)
            ),
        )
    command.finish(args, {"path": str(path) if path else None}, error, str(path))


def _watch_arguments(parser: argparse.ArgumentParser, purpose_default: str | None) -> None:
    parser.add_argument("lemon", help="Lemon-ID, channel or brief name of the lemon to watch")
    parser.add_argument("--purpose", default=purpose_default, help="Why you watch it")
    parser.add_argument(
        "--to",
        action="append",
        type=_to,
        default=[],
        metavar="STATUS",
        help="Wake on entry into this Status, or `needs` for a change of its Needs (repeatable; "
        "default: merge, done, needs). Exits, gone sessions and deaf or dead lemons always wake",
    )


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("lemon", help="Add, change or remove a row in ### Lemons")
    verbs = parser.add_subparsers(dest="verb", required=True)
    _watch_arguments(command.parser(verbs, "add", "Add or replace a lemon row"), "")
    _watch_arguments(command.parser(verbs, "set", "Change an existing lemon row"), None)
    command.parser(verbs, "rm", "Remove a lemon row").add_argument("lemon")
    parser.set_defaults(func=_cmd)
