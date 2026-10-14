"""`lemonaid hooks`: install lemonaid's lemon-side hooks in Claude Code and Codex, and run them."""

import argparse
import sys

from ..claude import waiter_check
from . import install, own_change, session_start


def _install(a: argparse.Namespace) -> None:
    for harness in install.HARNESSES if a.harness == "all" else (a.harness,):
        try:
            lines = (
                install.uninstall(harness)
                if a.uninstall
                else install.install(harness, dry_run=a.dry_run)
            )
        except ValueError as e:
            sys.exit(str(e))
        for line in lines:
            print(line)
    if "codex" in (a.harness, "all") and not (a.dry_run or a.uninstall):
        print(
            "Codex runs a new or changed hook only once it is trusted: review them in its /hooks."
        )


def setup_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "hooks",
        help="Install lemonaid's hooks in Claude Code and Codex, and the commands they run",
        description=install.__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="hooks_command", required=True)

    ap = sub.add_parser(
        "install",
        help="Add lemonaid's hooks to ~/.claude/settings.json and ~/.codex/hooks.json; "
        "other hooks are left alone, and installing twice changes nothing",
    )
    ap.add_argument("--harness", choices=[*install.HARNESSES, "all"], default="all")
    ap.add_argument("--dry-run", action="store_true", help="say what would change, change nothing")
    ap.add_argument("--uninstall", action="store_true", help="remove the hooks lemonaid installed")
    ap.set_defaults(func=_install)

    for name, help_text, run in (
        (
            "own-change",
            "PreToolUse/PostToolUse: record the session's own edits to watched docs, and its pushes",
            lambda a: own_change.handle(a.harness),
        ),
        (
            "stop",
            "Stop: block ending a turn while the attached brief's waiters aren't armed",
            lambda a: waiter_check.handle(harness=a.harness),
        ),
        (
            "session-start",
            "SessionStart: remind a lemon with an attached brief which waiters to arm",
            lambda a: session_start.handle(a.harness),
        ),
    ):
        hp = sub.add_parser(name, help=f"{help_text} (reads the hook's JSON from stdin)")
        hp.add_argument("--harness", choices=install.HARNESSES, required=True)
        hp.set_defaults(func=run)
