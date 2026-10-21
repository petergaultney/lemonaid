"""`lemonaid watch notes`: the event kinds a note can name, and the notes written for them."""

import argparse
import json
import sys

from ..skills import compose
from . import kinds, notes


def _list(a: argparse.Namespace) -> int:
    directory = notes.default_dir()
    loaded = notes.load(directory, a.harness)
    if a.json:
        print(
            json.dumps(
                {
                    "directory": str(directory),
                    "kinds": [
                        {"kind": kind, "description": what, "note": kind in loaded.notes}
                        for kind, what in kinds.KINDS.items()
                    ],
                    "problems": loaded.problems,
                },
                indent=2,
            )
        )
    else:
        print(f"Notes directory: {directory}")
        width = max(map(len, kinds.KINDS))
        for kind, what in kinds.KINDS.items():
            print(f"{'*' if kind in loaded.notes else ' '} {kind:<{width}}  {what}")
        for problem in loaded.problems:
            print(f"problem: {problem}", file=sys.stderr)
    return 1 if loaded.problems else 0


def _show(a: argparse.Namespace) -> int:
    if a.kind not in kinds.KINDS:
        print(f"{a.kind!r} is not an event kind; see `lemonaid watch notes list`", file=sys.stderr)
        return 2

    loaded = notes.load(notes.default_dir(), a.harness)
    if a.kind not in loaded.notes:
        print(f"no note for {a.kind} ({notes.default_dir() / a.kind}.md)", file=sys.stderr)
        return 1

    print(notes.appendix([a.kind], loaded.notes))
    return 0


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    ap = subparsers.add_parser(
        "notes", help="List event kinds and the notes appended to them", description=__doc__
    )
    sub = ap.add_subparsers(dest="notes_command", required=True)
    listing = sub.add_parser("list", help="every event kind, starred when a note exists")
    listing.add_argument("--json", action="store_true")
    listing.set_defaults(notes_func=_list)
    show = sub.add_parser("show", help="a note as one harness receives it")
    show.add_argument("kind")
    show.set_defaults(notes_func=_show)
    for parser in (listing, show):
        parser.add_argument("--harness", choices=compose.HARNESSES, default="claude")
    ap.set_defaults(func=lambda a: sys.exit(a.notes_func(a)))
