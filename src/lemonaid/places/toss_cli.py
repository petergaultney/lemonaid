"""`place toss`: the confirmation, and the two flags that skip parts of it.

The set being torn down is shown before anything happens, including whether a
session has no place and its directory work was not inspected.
"""

import argparse
import json
import sys

from ..config import load_config
from . import ownership, self_install, target, teardown, toss_warning


def _fate(place: ownership.Place, reasons: list[str]) -> str:
    """One line saying what happens to *place*, and anything you'd want to know first."""
    if not place.exists:
        return f"  {place.key} (already gone)"

    return f"  {place.key}" + (f" - {'; '.join(reasons)}" if reasons else "")


def _plural(n: int, noun: str) -> str:
    return f"{n} {noun}{'s' if n != 1 else ''}"


def _headline(doomed: target.TossTarget) -> str:
    if doomed.place is None:
        return f"session {doomed.session!r} (no place; directory work was not inspected)"

    if not doomed.session and not doomed.partial:
        return f"place {doomed.place.key!r} (no session)"

    return f"place {doomed.place.key!r}"


def _closures(doomed: target.TossTarget) -> list[str]:
    """One line per session that loses something, windows by their tmux IDs."""
    by_session: dict[str, list[str]] = {}
    for window, panes in doomed.partial.items():
        by_session.setdefault(panes[0].session, []).append(window)

    return [
        *(
            [f"  session {doomed.session!r} closes ({_plural(len(doomed.windows), 'window')})"]
            if doomed.session and doomed.place is not None
            else []
        ),
        *(
            f"  {_plural(len(ws), 'window')} in {session!r} "
            f"{'close' if len(ws) != 1 else 'closes'} ({', '.join(ws)}); the session stays"
            for session, ws in by_session.items()
        ),
    ]


def _describe(doomed: target.TossTarget, concerns: dict[str, list[str]]) -> list[str]:
    """What is about to happen, one line per thing it happens to."""
    return [
        _headline(doomed),
        *(_fate(place, concerns.get(place.key, [])) for place in doomed.places),
        *_closures(doomed),
        *(f"  window {window} stays open, in a released directory" for window in doomed.left_open),
    ]


def _prompt(doomed: target.TossTarget) -> str:
    if doomed.place is None:
        return "kill this session? [y/N] "

    if doomed.session:
        return "kill it and release the place? [y/N] "

    if doomed.partial:
        return f"close {_plural(len(doomed.partial), 'window')} and release the place? [y/N] "

    return "release it? [y/N] "


def _confirmed(doomed: target.TossTarget, concerns: dict[str, list[str]]) -> bool:
    for line in _describe(doomed, concerns):
        print(line, file=sys.stderr)

    toss_warning.show(doomed)
    prompt = _prompt(doomed)
    try:
        return input(prompt).strip().lower() in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        print(file=sys.stderr)
        return False


def cmd_toss(args: argparse.Namespace) -> None:
    """Tear down a tmux session and the places it occupies."""
    config = load_config()
    unattended = args.yes or args.json
    doomed, why_not = target.resolve_toss_target(config, args.key, unattended=unattended)
    if doomed is None:
        print(why_not, file=sys.stderr)
        sys.exit(1)

    if refusal := self_install.editable_install_refusal(doomed):
        print(refusal, file=sys.stderr)
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

    # The prompt may have sat for a while; what was confirmed has to still be true.
    if changed := target.changed_since(config, args.key, doomed, unattended=unattended):
        print(changed, file=sys.stderr)
        sys.exit(1)

    if refusal := self_install.editable_install_refusal(doomed):
        print(refusal, file=sys.stderr)
        sys.exit(1)

    error = teardown.toss(doomed.session, doomed.places, doomed.partial)

    if args.json:
        print(
            json.dumps(
                {
                    "session": doomed.session,
                    "released": [p.key for p in doomed.places],
                    "error": error,
                    "place": doomed.place.key if doomed.place else None,
                    "closed_windows": doomed.closing if not error else [],
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
        help="Release a place or close a named session with no place",
        description="A named target is a managed place when its directory exists or its root "
        "lists it; otherwise it can be an exact tmux session name with no managed place "
        "in its panes. A session-only toss closes the session without inspecting or releasing "
        "a directory. The unit for a managed place is its directory, plus the tmux session "
        "sitting in it when that session is dedicated to it (named for it, or entirely "
        "inside it, and holding no other managed place). With no key the place is the "
        "one the current directory is in, and a directory that is not in a place is "
        "refused rather than falling back to your session; with a key it is that place or "
        "session, from anywhere. Under --yes or --json, closing the session you are running in "
        "needs the key.\n\n"
        "In a session that also holds other places, only the windows sitting in this "
        "one close, and the session stays. A window with a pane in the place and a "
        "pane elsewhere refuses, naming both.\n\n"
        "Protected places (main, master by default) are never released and never "
        "count as held. Protected sessions are refused outright. A place containing "
        "the source of an editable lemonaid install is also refused. Teardown switches "
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
        help="The place to release or exact session name to close (default: place at cwd)",
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
