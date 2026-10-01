"""`brief check`: report what is wrong with a brief, and exit 1 if anything is."""

import argparse
import json
import sys
from pathlib import Path

from ..inbox import db
from . import attached, check, command, selector, store


def _live_briefs() -> list[tuple[Path, str]]:
    """(path, channel) of each brief attached to a session that isn't archived, or pending."""
    with db.connect() as conn:
        attached.claim_pending(conn)
        found = {
            a.path.resolve(): a.channel
            for a in attached.everything(conn)
            if not (a.notification and a.notification.is_archived)
        }
    return list(found.items())


def _cmd_check(args: argparse.Namespace) -> None:
    if args.all:
        targets = _live_briefs()
    else:
        path, error = (store.resolve(args.file), "") if args.file else command.own_brief(args)
        if path is None or not path.is_file():
            command.finish(args, {"path": None, "problems": []}, error or f"No brief at {path}")
            return

        targets = [(path, "")]

    with db.connect() as conn:
        results = [
            {
                "path": str(path),
                "channel": channel or None,
                "problems": (
                    check.problems(conn, path, path.read_text())
                    if path.is_file()
                    else ["The attached brief does not exist"]
                ),
            }
            for path, channel in targets
        ]

    failing = [r for r in results if r["problems"]]
    if args.json:
        print(json.dumps(results if args.all else {**results[0], "error": None}))
    for result in [] if args.json else failing:
        name = Path(result["path"]).name
        print("\n".join(f"{name}: {p}" for p in result["problems"]), file=sys.stderr)
    if not args.json and args.all:
        print(f"{len(results) - len(failing)} of {len(results)} briefs pass")
    elif not args.json and not failing:
        print(f"{Path(results[0]['path']).name}: ok")
    if failing:
        sys.exit(1)


def add_parsers(brief_subparsers: argparse._SubParsersAction) -> None:
    summary = "Report what is wrong with a brief's layout or Lemon-ID; exit 1 if anything is"
    parser = brief_subparsers.add_parser(
        "check",
        help=summary,
        description=f"{summary}. Run it after editing a brief by hand.",
    )
    selector.add_arguments(parser, required=False)
    parser.add_argument(
        "file", nargs="?", default="", help="A brief file instead of a lemon's attached one"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Every brief attached to a session that isn't archived, or waiting for one",
    )
    parser.add_argument("--json", action="store_true", help="Print the result as JSON")
    parser.set_defaults(func=_cmd_check)
