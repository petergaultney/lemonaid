"""`lemonaid for-lemons`: print the guide for automated callers.

An agent reaches lemonaid through the CLI and has no reason to know where a
markdown file lives in a checkout it may not be sitting in. The same guide humans
read in `docs/` is installed alongside the package, so one command gets it
whatever the install looks like.
"""

import argparse
import re
import sys
from collections import abc
from pathlib import Path

from .config import load_config

_INSTALLED = Path(__file__).parent / "docs" / "for-lemons.md"
# An editable install points at the source tree, where docs/ is a sibling of src/.
_IN_CHECKOUT = Path(__file__).parent.parent.parent / "docs" / "for-lemons.md"


def guide_path() -> Path | None:
    return next((path for path in (_INSTALLED, _IN_CHECKOUT) if path.is_file()), None)


def auto_read_section(patterns: abc.Sequence[re.Pattern[str]]) -> str:
    """This machine's `[inbox] auto_read` patterns, for lemons deciding how to end a turn."""
    if not patterns:
        return (
            "\n## Auto-read on this machine\n\n"
            "No `[inbox] auto_read` patterns are configured, so every finished turn "
            "marks its session unread.\n"
        )

    return "\n".join(
        [
            "",
            "## Auto-read on this machine",
            "",
            "A finished turn whose final message matches one of these regexes, from its "
            "start, leaves your session read instead of unread. Begin the final message "
            "with a match only when the user has nothing to look at.",
            "",
            *(f"- `{pattern.pattern}`" for pattern in patterns),
            "",
        ]
    )


def cmd_for_lemons(args: argparse.Namespace) -> None:
    """Print the programmatic-access guide."""
    path = guide_path()
    if path is None:
        print(
            "The for-lemons guide is not installed. It lives at docs/for-lemons.md "
            "in the lemonaid repository.",
            file=sys.stderr,
        )
        sys.exit(1)

    if args.path:
        print(path)
        return

    print(path.read_text(), end="")
    print(auto_read_section(load_config().inbox.auto_read), end="")


def setup_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "for-lemons",
        help="Print the guide for lemons and other automated callers",
        description="Everything an agent needs to drive lemonaid: the inbox JSON "
        "surface, and how places (directories and their tmux sessions) are opened, "
        "listed, and torn down. Read this before scripting against lemonaid.",
    )
    parser.add_argument(
        "--path", action="store_true", help="Print the guide's location instead of its contents"
    )
    parser.set_defaults(func=cmd_for_lemons)
