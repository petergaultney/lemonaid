"""`place toss`: the confirmation, and the two flags that skip parts of it.

The set being torn down is shown before anything happens, including whether a
session has no place and its directory work was not inspected.
"""

import argparse
import json
import sys
from pathlib import Path

from ..config import load_config
from . import ownership, self_install, target, teardown, toss_warning


def _label(place: ownership.Place) -> str:
    return f"{place.key} ({place.root.path})"


def _fate(place: ownership.Place, reasons: list[str]) -> str:
    """One line saying what happens to *place*, and anything you'd want to know first."""
    if not place.exists:
        return f"  {_label(place)} (already gone)"

    return f"  {_label(place)}" + (f" - {'; '.join(reasons)}" if reasons else "")


def _plural(n: int, noun: str) -> str:
    return f"{n} {noun}{'s' if n != 1 else ''}"


def _headline(doomed: target.TossTarget) -> str:
    if doomed.session:
        return f"workspace {doomed.session!r}"

    if doomed.place is None:
        return "no workspace or directory"

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
            if doomed.session
            else []
        ),
        *(
            f"  {_plural(len(ws), 'window')} in {session!r} "
            f"{'close' if len(ws) != 1 else 'closes'} ({', '.join(ws)}); the session stays"
            for session, ws in by_session.items()
        ),
    ]


def _describe(doomed: target.TossTarget, concerns: dict[Path, list[str]]) -> list[str]:
    """What is about to happen, one line per thing it happens to."""
    return [
        _headline(doomed),
        *(_fate(place, concerns.get(place.directory, [])) for place in doomed.places),
        *_closures(doomed),
        *(f"  window {window} stays open, in a released directory" for window in doomed.left_open),
        *(f"  {note}" for note in doomed.kept),
    ]


def _prompt(doomed: target.TossTarget, default_yes: bool) -> str:
    choice = "[Y/n] " if default_yes else "[y/N] "
    if doomed.place is None:
        return f"close this workspace? {choice}"

    if doomed.session:
        return f"close it and release the directories? {choice}"

    if doomed.partial:
        return f"close {_plural(len(doomed.partial), 'window')} and release the place? {choice}"

    return f"release it? {choice}"


def _confirmed(doomed: target.TossTarget, concerns: dict[Path, list[str]]) -> bool:
    for line in _describe(doomed, concerns):
        print(line, file=sys.stderr)

    lemons = toss_warning.affected(doomed)
    toss_warning.show(doomed, lemons)
    default_yes = not (
        any(concerns.values())
        or lemons
        or doomed.kept
        or doomed.partial
        or doomed.left_open
        or any(not place.exists for place in doomed.places)
    )
    prompt = _prompt(doomed, default_yes)
    try:
        answer = input(prompt).strip().lower()
        return answer in ("y", "yes") or (default_yes and not answer)
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

    concerns = {place.directory: teardown.concerns(place) for place in doomed.places}

    if any(concerns.values()) and not args.force:
        print("There is unfinished work here:", file=sys.stderr)
        for place in doomed.places:
            for reason in concerns[place.directory]:
                print(f"  {_label(place)}: {reason}", file=sys.stderr)
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
                    "kept": list(doomed.kept),
                    "error": error,
                    "place": doomed.place.key if doomed.place else None,
                    "closed_windows": doomed.closing if not error else [],
                    "session_closed": bool(doomed.session) and not error,
                }
            )
        )
    elif error:
        print(error, file=sys.stderr)

    if args.yes and not args.json:
        for note in doomed.kept:
            print(note, file=sys.stderr)

    if error:
        sys.exit(1)


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "toss",
        help="Close a single-purpose workspace with optional directory cleanup",
        description="Close a one-off tmux workspace and release its associated directories "
        "through configured destroy hooks. Hybrid workspaces with lemons in unrelated "
        "places are refused, even with --force. With no identifiable lemons, directory "
        "cleanup requires consistent pane directories. A named tmux session is selected before a "
        "same-named directory. With no name, an interactive toss targets the current "
        "tmux session; --yes and --json require its name. Outside tmux, or when the "
        "name has no session, directory-only targeting remains available.\n\n"
        "Protected sessions are refused. Protected directories, directories used by "
        "surviving workspaces, and directories whose ownership cannot be established "
        "stay. The confirmation lists them. A failed directory-discovery hook does "
        "not prevent session closure. Unfinished work still requires --force. "
        "Teardown switches clients elsewhere first and runs detached, logging to "
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
        help="Workspace to close, or directory key (default: current tmux workspace)",
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
