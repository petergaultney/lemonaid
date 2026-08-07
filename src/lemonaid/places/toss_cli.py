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

    return f"session {doomed.session!r}"


def _describe(doomed: target.TossTarget, concerns: dict[str, list[str]]) -> list[str]:
    """What is about to happen, one line per thing it happens to."""
    return [
        _headline(doomed),
        *(_fate(place, concerns.get(place.key, [])) for place in doomed.places),
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

    error = teardown.toss(doomed.session, doomed.places, from_inside=doomed.from_inside)

    if args.json:
        # The whole set is reported: a named toss acts on everything its session
        # owns, which may be more than the caller named.
        print(
            json.dumps(
                {
                    "session": doomed.session,
                    "released": [p.key for p in doomed.places],
                    "error": error,
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
        help="Kill a tmux session and release the places it occupies",
        description="The unit is a tmux session and every managed place its panes "
        "sit in. With no key that is the session you are attached to; with a key it "
        "is the session sitting in that place.\n\n"
        "A KEY NAMES A SESSION, NOT JUST A DIRECTORY: tossing one key releases "
        "everything that session occupies, which may be more than you named. The set "
        "is listed and confirmed first, and reported back under 'released'. Run "
        "`place list --json` and look at the `session` field if you need to know "
        "which places go together before acting.\n\n"
        "Protected places (main, master by default) are never released and never "
        "count as owned. Protected sessions are refused outright. Teardown switches "
        "you away first, then runs detached, logging to "
        "~/.local/state/lemonaid/reap.log.",
        epilog="Examples:\n"
        "  place toss feat/thing --json   # what an agent should use: names the target\n"
        "  place toss                     # the session you're attached to\n"
        "  place list --json              # which session occupies which place",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "key",
        nargs="?",
        help="A place whose session to tear down (default: the session you're attached to)",
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
