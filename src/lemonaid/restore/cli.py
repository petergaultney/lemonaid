"""`lemonaid restore <terminal>`: put the lemons back, and say which ones came back working."""

import argparse
import json
import sys
import time
from collections import abc

from ..brief import attached
from ..config import load_config
from ..inbox import db
from ..tmux import inspect as tmux_inspect
from ..tmux import restore as tmux_restore
from . import prompt, report

_DEFAULT_WAIT_SECONDS = 180


def _prompts(rows: abc.Sequence[db.Notification]) -> dict[str, str]:
    """The rearm prompt of each row with an attached brief that can be read."""
    with db.connect() as conn:
        briefs = attached.for_rows(conn, rows)

    prompts: dict[str, str] = {}
    for channel, path in briefs.items():
        try:
            prompts[channel] = prompt.rearm(path, path.read_text(), channel.partition(":")[0])
        except OSError as e:
            print(f"cannot read the brief of {channel} ({path}): {e}", file=sys.stderr)

    return prompts


def _activity() -> dict[str, float]:
    """When the inbox last heard from each channel."""
    with db.connect() as conn:
        return {row.channel: max(row.created_at, row.turn_at or 0.0) for row in db.get_active(conn)}


def _progress(line: str) -> None:
    print(f"  {line}", file=sys.stderr, flush=True)


def _unplaced(
    rows: abc.Sequence[db.Notification], plans: abc.Sequence[tmux_restore.SessionPlan]
) -> list[report.Result]:
    planned = {w.channel for plan in plans for w in plan.windows}
    return [
        report.Result(
            row.channel,
            row.name or row.channel,
            "",
            report.NOT_RESTORED,
            "no recorded tmux window, or no way to resume it",
        )
        for row in rows
        if row.channel not in planned
    ]


def cmd_tmux(args: argparse.Namespace) -> None:
    """Rebuild the tmux layout the inbox describes, and wait for its lemons to start working."""
    config = load_config()
    with db.connect() as conn:
        rows = db.get_active(conn, switch_source="tmux")

    plans = tmux_restore.plan_restore(rows, config, _prompts(rows))

    if args.dry_run:
        if args.json:
            print(json.dumps(tmux_restore.as_json(plans)))
            return

        for line in tmux_restore.describe(plans):
            print(line)
        return

    started = time.time()
    done = tmux_restore.restore(plans)
    results = [
        *(
            report.wait(
                done.placed,
                started,
                started + args.wait,
                _activity,
                tmux_inspect.seen,
                _progress if not args.json else lambda _: None,
            )
            if args.wait > 0
            else []
        ),
        *done.failed,
        *_unplaced(rows, plans),
    ]

    if args.json:
        print(
            json.dumps(
                {
                    "restored": done.restored,
                    "skipped": done.skipped,
                    "lemons": [r._asdict() for r in results],
                }
            )
        )
    else:
        for name in done.restored:
            print(f"restored {name}")

        # Not stderr: an already-running session is the expected outcome of
        # running this when nothing is wrong, not a problem with the run.
        for name in done.skipped:
            print(f"skipped {name} (already running)")

        if not plans:
            print(tmux_restore.describe(plans)[0])

        if results:
            print("", *report.describe(results), sep="\n")

        print(f"\nrestored {len(done.restored)}, skipped {len(done.skipped)} already running")

    if any(r.outcome not in report.OK for r in results):
        sys.exit(1)


def add_tmux_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the layout that would be rebuilt, and start nothing",
    )
    parser.add_argument(
        "--wait",
        type=int,
        default=_DEFAULT_WAIT_SECONDS,
        metavar="SECONDS",
        help="How long to wait for prompted lemons to start working before reporting "
        f"(default {_DEFAULT_WAIT_SECONDS}; 0 reports nothing)",
    )
    parser.add_argument("--json", action="store_true", help="Print the result as JSON")
    parser.set_defaults(func=cmd_tmux)


TMUX_DESCRIPTION = (
    "Recreates the tmux sessions the inbox says its active lemons were running in, "
    "resuming each one in the window it occupied, and starts each lemon with a prompt "
    "to rearm the waiters listed under ## Waiters in its brief.\n\n"
    "Windows keep their recorded index, so a window lemonaid knows nothing about - an "
    "editor, a shell - comes back as an empty gap rather than shifting the others down. "
    "Restored sessions are detached. A session that is already running is left alone, so "
    "this is safe to run after rebuilding some of them by hand.\n\n"
    "It then waits for each prompted lemon to be heard from in the inbox, and reports every "
    "lemon as working, stuck (its pane's last lines say why), exited, no brief, nothing to "
    "rearm, rearm by hand (a harness that can't be started on a prompt), or not restored. "
    "It exits 1 if any lemon is stuck, exited, has to be rearmed by hand, or wasn't restored."
)


def setup_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "restore",
        help="Bring lemons back to work after their terminal went away",
        description="Resumes the inbox's active lemons in the terminal they were running "
        "in, and starts each with a prompt to rearm its brief's waiters.",
    )
    terminals = parser.add_subparsers(dest="terminal")
    add_tmux_arguments(
        terminals.add_parser(
            "tmux",
            help="Rebuild the tmux sessions the inbox describes",
            description=TMUX_DESCRIPTION,
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
    )
    parser.set_defaults(func=lambda a: parser.print_help())
