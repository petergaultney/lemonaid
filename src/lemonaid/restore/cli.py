"""`lemonaid restore`: bring lost lemons back, each proven running, and report the rest.

Each lost lemon is restored by the front end (terminal) it ran in; this knows none of
them by name.
"""

import argparse
import json
import sys
import time
import typing as ty
from collections import abc

from ..brief import attached, identity
from ..config import Config, load_config
from ..inbox import db, ended
from ..launch.restart import native
from . import auto, dismiss, front_ends, inbox_report, loss, plan, report, run, wake

_DEFAULT_WAIT_SECONDS = 180


def _briefs(rows: abc.Sequence[db.Notification]) -> dict[str, plan.Brief]:
    """The brief of each row that has one that can be read."""
    with db.connect() as conn:
        paths = attached.for_rows(conn, rows)

    briefs: dict[str, plan.Brief] = {}
    for channel, path in paths.items():
        try:
            text = path.read_text()
            briefs[channel] = plan.Brief(identity.read(text), text, path)
        except (OSError, ValueError) as e:
            print(f"cannot read the brief of {channel} ({path}): {e}", file=sys.stderr)

    return briefs


def _activity() -> dict[str, float]:
    """When the inbox last heard from each channel."""
    with db.connect() as conn:
        return {row.channel: max(row.created_at, row.turn_at or 0.0) for row in db.get_active(conn)}


def _progress(line: str) -> None:
    print(f"  {line}", file=sys.stderr, flush=True)


def _quiet(line: str) -> None:
    pass


def _lost(dry_run: bool) -> list[db.Notification]:
    """Every lemon lost with its terminal, including any no inbox watcher has marked yet.

    Marks those, unless *dry_run*.
    """
    with db.connect() as conn:
        if not dry_run:
            loss.mark(conn, by="restore")
        rows = loss.candidates(conn)

    return loss.restorable(rows)


class _Planned(ty.NamedTuple):
    group: front_ends.Group
    running: set[str]  # lost lemons running now, resumed by hand
    plan: plan.Plan


def _plan(group: front_ends.Group, config: Config, dry_run: bool) -> _Planned:
    running = group.terminal.found(group.rows, dry_run)
    rows = [row for row in group.rows if row.channel not in running]
    return _Planned(
        group,
        running,
        plan.build(rows, group.terminal.place, config, _briefs(rows), native.recorded_argv),
    )


def _dry_run(planned: abc.Sequence[_Planned], unable: list[report.Result], as_json: bool) -> None:
    relinked = [terminal.relink(True) for terminal in front_ends.restorers()]
    if as_json:
        print(
            json.dumps(
                {
                    "lemons": [lemon for each in planned for lemon in plan.as_json(each.plan)],
                    "not_restored": [
                        r._asdict()
                        for r in [*(r for each in planned for r in each.plan.skipped), *unable]
                    ],
                    "running": sorted(c for each in planned for c in each.running),
                    "relinked": [entry for each in relinked for entry in each.json],
                }
            )
        )
        return

    lines = [
        *(line for each in planned for line in plan.describe(each.plan)),
        *(f"{'not restored':<24} {r.name}  ({r.detail})" for r in unable),
        *(line for each in relinked for line in each.lines),
    ]
    print(*(lines or [plan.NOTHING]), sep="\n")


class _Done(ty.NamedTuple):
    started: list[run.Lemon]
    results: list[report.Result]


def _restore_group(
    each: _Planned, config: Config, args: argparse.Namespace, deadline: float
) -> _Done:
    terminal = each.group.terminal
    progress = _progress if not args.json else _quiet
    started_at = time.time()
    started, failed = run.start(
        each.plan.lemons,
        terminal,
        config.restore.parallel,
        config.restore.verify_seconds,
        progress,
    )
    with db.connect() as conn:
        placed, unsettled = wake.settle_all(
            conn, started, lambda lemon: lemon.spot.where, config, each.group.prompt
        )
    waited = (
        report.wait(placed, started_at, deadline, _activity, terminal.seen, progress)
        if args.wait > 0
        else [report.Result(p.channel, p.name, p.where, p.rearm, "") for p in placed]
    )
    return _Done(
        started,
        [
            *(
                report.Result(row.channel, row.name or row.channel, "", report.RUNNING, "")
                for row in each.group.rows
                if row.channel in each.running
            ),
            *waited,
            *unsettled,
            *failed,
            *each.plan.skipped,
        ],
    )


def _restore(
    args: argparse.Namespace, config: Config, lost: list[db.Notification]
) -> tuple[list[db.Notification], bool]:
    """Restore *lost*: (the lemons left waiting for their terminal to run again, whether
    any lemon is not back to work)."""
    start = not (args.into_running or args.auto)
    groups, unable = front_ends.groups(lost, start)
    waiting: list[db.Notification] = []
    if not start:
        up = [(group, group.terminal.up()) for group in groups]
        waiting = [row for group, running in up if not running for row in group.rows]
        groups = [group for group, running in up if running]
    planned = [_plan(group, config, args.dry_run) for group in groups]
    if args.dry_run:
        _dry_run(planned, unable, args.json)
        return waiting, False

    deadline = time.time() + args.wait
    done = [_restore_group(each, config, args, deadline) for each in planned]
    started = [lemon for each in done for lemon in each.started]
    running = sorted(c for each in planned for c in each.running)
    results = [*(r for each in done for r in each.results), *unable]
    with db.connect() as conn:
        missing = inbox_report.post(
            conn, [r for r in results if args.wait > 0 or r.outcome != report.PROMPTED]
        )
    relinked = [terminal.relink(False) for terminal in front_ends.restorers()]

    if args.json:
        print(
            json.dumps(
                {
                    "restored": [lemon.channel for lemon in started],
                    "running": running,
                    "lemons": [r._asdict() for r in results],
                    "relinked": [entry for each in relinked for entry in each.json],
                    "waiting": [row.channel for row in waiting],
                }
            )
        )
    else:
        relink_lines = [line for each in relinked for line in each.lines]
        if not lost:
            print(plan.NOTHING)
        if results:
            print(*report.describe(results), sep="\n")
        if relink_lines:
            print("", *relink_lines, sep="\n")
        if waiting:
            print(f"\n{len(waiting)} lost lemons wait for their terminal to run again")
        print(
            f"\nrestored {len(started)}, {len(running)} already running, "
            f"{len(missing)} not back to work"
        )

    return waiting, bool(missing)


def cmd_restore(args: argparse.Namespace) -> None:
    """Bring back every lemon lost with its terminal, and report each one.

    With `--auto` it does what `[restore] auto` says, so a trigger and a person run the
    same command; the lock makes concurrent runs one.
    """
    config = load_config()
    if args.dry_run:
        _restore(args, config, _lost(dry_run=True))
        return

    if args.auto and config.restore.auto == "off":
        return

    with auto.lock() as held:
        if not held:
            print("Another restore is running; it will do this one's work.", file=sys.stderr)
            sys.exit(0 if args.auto else 1)

        lost = [
            row for row in _lost(dry_run=False) if not args.auto or ended.lost(row.metadata)
        ]  # a trigger means a lost server; a crash waits to be restored by hand
        with db.connect() as conn:
            if args.auto and config.restore.auto == "ask":
                auto.ask(conn, lost)
                return

            auto.restoring(conn, lost)
        waiting: list[db.Notification] = []
        try:
            waiting, missing = _restore(args, config, lost)
        finally:
            with db.connect() as conn:
                auto.ask(conn, waiting)

    if missing:
        sys.exit(1)


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print where each lost lemon would go, and start nothing",
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
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Run as a trigger does: follow [restore] auto (off, ask or on); implies "
        "--into-running",
    )
    parser.add_argument(
        "--into-running",
        action="store_true",
        help="Restore only into a terminal that runs now, never starting one; the rest wait",
    )
    parser.set_defaults(func=cmd_restore)


DESCRIPTION = (
    "Brings back every lemon lost with its terminal: for tmux, no server runs on its "
    "recorded socket, or a newer one replaced it. It also brings back every lemon whose harness "
    "crashed: it stopped without reporting a quit while its pane ran. Run it again at any time; "
    "it does only what is still undone.\n\n"
    "A lost lemon already running somewhere (resumed by hand) has its row pointed at its "
    "pane. A crashed lemon goes back into its own pane when that is idle at a shell. Each "
    "other one goes back to its recorded window, or the next free index when "
    "that is taken, in a session recreated if it is missing; a running session gains the "
    "windows it lacks and nothing in it is touched. Each is resumed with the model and "
    "effort it was started with. A lemon recorded on another tmux server than the one restore "
    "opens windows on is not restored.\n\n"
    "Lemons start a few at a time ([restore] parallel). Each counts as restored only when "
    "its own conversation runs in its window; one that doesn't is stopped and started once "
    "more, then reported. A restored lemon whose push scout runs gets its subscriptions back "
    "with no prompt; one that can't be pushed to is prompted to rearm its brief's waiters.\n\n"
    "It waits for each prompted lemon to be heard from, reports every lemon, and lists the "
    "ones not back to work in one inbox row (lemonaid:restore). It exits 1 if any is not."
)


def setup_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "restore",
        help="Bring back the lemons lost when their terminal went away",
        description=DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    add_arguments(parser)
    commands = parser.add_subparsers(dest="restore_command")
    add_arguments(
        commands.add_parser(
            "tmux",
            help="Same as `lemonaid restore`",
            description=DESCRIPTION,
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
    )
    dismiss.setup_parser(commands)
