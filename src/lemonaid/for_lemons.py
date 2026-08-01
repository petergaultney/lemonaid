"""`lemonaid for-lemons`: print the guide for automated callers.

An agent reaches lemonaid through the CLI and has no reason to know where a
markdown file lives in a checkout it may not be sitting in. The same guide humans
read in `docs/` is installed alongside the package, so one command gets it
whatever the install looks like.
"""

import argparse
import sys
from pathlib import Path

_INSTALLED = Path(__file__).parent / "docs" / "for-lemons.md"
# An editable install points at the source tree, where docs/ is a sibling of src/.
_IN_CHECKOUT = Path(__file__).parent.parent.parent / "docs" / "for-lemons.md"


def guide_path() -> Path | None:
    return next((path for path in (_INSTALLED, _IN_CHECKOUT) if path.is_file()), None)


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
