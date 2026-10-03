"""`place toss`: the confirmation, and the two flags that skip parts of it.

The set being torn down is shown before anything happens, because that is the
decision - at teardown time you know whether the second worktree should go too,
and you will not know it later.
"""

import argparse
import json
import sys

from ..config import load_config
from . import ownership, target, teardown


def _fate(place: ownership.Place, reasons: list[str]) -> str:
    """One line saying what happens to *place*, and anything you'd want to know first."""
    if not place.exists:
        return f"  {place.key} (already gone)"

    return f"  {place.key}" + (f" - {'; '.join(reasons)}" if reasons else "")


def _headline(doomed: target.TossTarget) -> str:
    """The thing being torn down, named as whatever it actually is."""
    if not doomed.session:
        return f"place {doomed.places[0].key!r} (no session)"

    if not doomed.places:
        return f"session {doomed.session!r} - no managed places to release"

    n = len(doomed.windows)
    return f"session {doomed.session!r}, {n} window{'s' if n != 1 else ''}"


def _describe(doomed: target.TossTarget, concerns: dict[str, list[str]]) -> list[str]:
    """What is about to happen, one line per thing it happens to."""
    return [
        _headline(doomed),
        *(_fate(place, concerns.get(place.key, [])) for place in doomed.places),
        *(f"  window {window} stays open, in a released directory" for window in doomed.left_open),
    ]


def _prompt(doomed: target.TossTarget) -> str:
    releasing = len(doomed.places)
    if not doomed.session:
        return "release it? [y/N] "

    if not releasing:
        return "kill it? [y/N] "

    return f"kill it and release {releasing} place{'s' if releasing != 1 else ''}? [y/N] "


def _confirmed(doomed: target.TossTarget, concerns: dict[str, list[str]]) -> bool:
    for line in _describe(doomed, concerns):
        print(line, file=sys.stderr)

    prompt = _prompt(doomed)
    try:
        return input(prompt).strip().lower() in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        print(file=sys.stderr)
        return False


def cmd_toss(args: argparse.Namespace) -> None:
    """Tear down a tmux session and the places it occupies."""
    doomed, why_not = target.resolve_toss_target(load_config(), args.key)
    if doomed is None:
        print(why_not, file=sys.stderr)
        sys.exit(1)

    concerns = {place.key: teardown.concerns(place) for place in doomed.places}

    if any(concerns.values()) and not args.force:
        print("There is unfinished work here:", file=sys.stderr)
        for key, reasons in concerns.items():
            for reason in reasons:
                print(f"  {key}: {reason}", file=sys.stderr)
        print("Pass --force to tear it down anyway.", file=sys.stderr)
        sys.exit(1)

    # --json implies --yes: there is no terminal to prompt on.
    if not (args.yes or args.json) and not _confirmed(doomed, concerns):
        print("Nothing was torn down.", file=sys.stderr)
        sys.exit(1)

    error = teardown.toss(doomed.session, doomed.places)

    if args.json:
        print(
            json.dumps(
                {
                    "session": doomed.session,
                    "released": [p.key for p in doomed.places],
                    "error": error,
                    "place": doomed.place.key if doomed.place else None,
                    "closed_windows": doomed.windows if not error else [],
                    "session_closed": bool(doomed.session) and not error,
                }
            )
        )
    elif error:
        print(error, file=sys.stderr)

    if error:
        sys.exit(1)


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "toss",
        help="Release a place and close the tmux session dedicated to it",
        description="The unit is a managed place: a directory, plus the tmux session "
        "sitting in it when that session is dedicated to it (named for it, or entirely "
        "inside it, and holding no other managed place). With no key the place is the "
        "one the current directory is in; with a key it is that place, from anywhere.\n\n"
        "A session that also holds other places is shared, and this release refuses "
        "to touch it: the message names the windows in the place, and closing them "
        "yourself lets the directory be released. A window with a pane in the place "
        "and a pane elsewhere refuses as well.\n\n"
        "Protected places (main, master by default) are never released and never "
        "count as held. Protected sessions are refused outright. Teardown switches "
        "every client attached to the session elsewhere first (or refuses if one has "
        "nowhere to go), then runs detached, logging to "
        "~/.local/state/lemonaid/reap.log.",
        epilog="Examples:\n"
        "  place toss feat/thing --json   # what an agent should use: names the place\n"
        "  place toss                     # the place the current directory is in\n"
        "  place list --json              # which session sits in which place",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "key",
        nargs="?",
        help="The place to release (default: the one the current directory is in)",
    )
    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Don't ask for confirmation. Still refuses if there is unpushed work.",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Tear down even though inspect reports uncommitted or unpushed work. "
        "Does not override protection.",
    )
    parser.add_argument(
        "--json", action="store_true", help="Print the result as JSON (implies --yes)"
    )
    parser.set_defaults(func=cmd_toss)
