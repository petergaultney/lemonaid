"""What every `brief` subcommand that acts for one lemon shares: its arguments and its output."""

import argparse
import json
import sys
from pathlib import Path

from ..inbox import db
from . import attached, selector, store


def finish(args: argparse.Namespace, result: dict, error: str, message: str = "") -> None:
    if args.json:
        print(json.dumps({**result, "error": error or None}, ensure_ascii=False))
    elif error:
        print(error, file=sys.stderr)
    elif message:
        print(message)

    if error:
        sys.exit(1)


def own_brief(args: argparse.Namespace) -> tuple[Path | None, str]:
    with db.connect() as conn:
        chosen, error = selector.select(conn, args)
        if chosen is None:
            return None, error

        attached.claim_pending(conn)
        path = attached.by_channel(conn, [chosen.channel]).get(chosen.channel)

    if path is None:
        return None, "No brief attached; `lemonaid brief attach --self <file>` or `brief new`"

    if error := store.outside_error(path):
        return None, error

    if not path.is_file():
        return None, f"The attached brief {path} does not exist"

    return path, ""


def parser(
    subparsers: argparse._SubParsersAction,
    name: str,
    summary: str,
    with_target: bool = True,
    target_required: bool = True,
) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(name, help=summary, description=summary)
    if with_target:
        selector.add_arguments(parser, required=target_required)
    parser.add_argument("--json", action="store_true", help="Print the result as JSON")
    return parser
