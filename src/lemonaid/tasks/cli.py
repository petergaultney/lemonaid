"""`lemonaid task`: list, show and export task objects, and replay a checker offline."""

import argparse
import json
import shlex
import sys
from pathlib import Path

from ..inbox import db
from . import cli_common, holding_cli, lifecycle_cli, observe_cli
from .checker import corpus, replay
from .inspection import inspect_cli
from .model import associations, dependencies, holding, ledger, tree


def _line(task: dict) -> str:
    url = f"  {task['subject_url']}" if task["subject_url"] else ""
    return f"task:{task['task_id']}  {task['holder']}  {task['description']}{url}"


def _cmd_list(args: argparse.Namespace) -> None:
    with db.connect() as conn:
        try:
            if args.tree:
                found = tree.rows(conn, cli_common.brief_id(conn, args.tree), args.include_closed)
            else:
                found = holding.held_by(conn, cli_common.brief_id(conn, args.holder))
        except cli_common.Failed as error:
            cli_common.fail(args, str(error))
    lines = [
        _line(t) + "".join(f"\n    {c['kind']}: {c['brief_id']}" for c in t.get("connections", []))
        for t in found
    ]
    cli_common.emit(args, {"tasks": found}, "\n".join(lines) or "no tasks")


def _cmd_show(args: argparse.Namespace) -> None:
    with db.connect() as conn:
        try:
            task = cli_common.task_id(args.task)
        except cli_common.Failed as error:
            cli_common.fail(args, str(error))
        state = ledger.state(conn, task)
        if state is None:
            cli_common.fail(args, f"no task:{task}")
        shown = {
            **state,
            "briefs": associations.links_of(conn, task),
            "waits_for": dependencies.waits_for(conn, task),
            "events": ledger.history(conn, task),
        }
    events = "".join(f"\n  r{e['revision']} {e['kind']} by {e['actor']}" for e in shown["events"])
    cli_common.emit(args, shown, _line(state) + events)


def _cmd_export(args: argparse.Namespace) -> None:
    with db.connect() as conn:
        ids = [
            row["task_id"] for row in conn.execute("SELECT task_id FROM tasks ORDER BY created_at")
        ]
        exported = [
            {
                **(ledger.state(conn, t) or {}),
                "briefs": associations.links_of(conn, t),
                "events": ledger.history(conn, t),
            }
            for t in ids
        ]
    print(json.dumps({"tasks": exported}, ensure_ascii=False, indent=2))


def _cmd_replay(args: argparse.Namespace) -> None:
    try:
        snapshots = corpus.load(args.corpus)
    except corpus.CorpusError as error:
        cli_common.fail(args, str(error))
    argv = shlex.split(args.checker) if args.checker else list(replay.DEFAULT_CHECKER)
    verdicts = list(replay.replay(argv, snapshots, args.timeout))
    baseline = replay.load_baseline(args.baseline) if args.baseline else {}
    changed = list(replay.changed(verdicts, baseline))
    if args.write_baseline:
        replay.write_baseline(args.write_baseline, verdicts)
    if args.json:
        print(
            json.dumps(
                {
                    "verdicts": [v._asdict() for v in verdicts],
                    "changed": [
                        {
                            "snapshot": v.snapshot,
                            "task_id": v.task_id,
                            "verdict": v.verdict,
                            "compared": why,
                        }
                        for v, why in changed
                    ],
                },
                ensure_ascii=False,
            )
        )
    else:
        for v, why in changed:
            print(f"{v.snapshot}/{v.task_id}: {v.verdict} ({why})")
        print(f"{len(verdicts)} verdicts, {len(changed)} changed", file=sys.stderr)
    if changed:
        raise SystemExit(1)


def setup_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "task",
        help="Task objects: who holds each unfinished piece of work",
        description="A task has a stable ID, one holder at a time, and an event history. "
        "Briefs specify the work; tasks record who must act on it next.",
    )
    tasks = parser.add_subparsers(dest="task_command", required=True)

    listing = tasks.add_parser("list", help="Open tasks a brief holds, or its whole tree's")
    which = listing.add_mutually_exclusive_group(required=True)
    which.add_argument("--holder", metavar="BRIEF", help="Tasks BRIEF (or self) holds")
    which.add_argument(
        "--tree",
        metavar="BRIEF",
        help="Tasks BRIEF or its descendants hold or specify",
    )
    listing.add_argument(
        "--include-closed", action="store_true", help="With --tree, closed ones too"
    )
    listing.add_argument("--json", action="store_true", help="Print the result as JSON")
    listing.set_defaults(func=_cmd_list)

    show = tasks.add_parser("show", help="One task, its briefs and its history")
    show.add_argument("task", metavar="TASK_ID")
    show.add_argument("--json", action="store_true", help="Print the result as JSON")
    show.set_defaults(func=_cmd_show)

    export = tasks.add_parser("export", help="Every task with its events, as JSON")
    export.add_argument("--json", action="store_true", help="Accepted; export is always JSON")
    export.set_defaults(func=_cmd_export)

    replaying = tasks.add_parser("replay", help="Run a checker over a saved corpus, offline")
    replaying.add_argument("corpus", type=Path, help="A corpus JSON file")
    replaying.add_argument(
        "--checker", default="", help="The checker command (default: the example)"
    )
    replaying.add_argument("--baseline", type=Path, help="Earlier verdicts to compare against")
    replaying.add_argument("--write-baseline", type=Path, help="Save these verdicts as a baseline")
    replaying.add_argument("--timeout", type=float, default=30.0, help="Seconds per evaluation")
    replaying.add_argument("--json", action="store_true", help="Print the result as JSON")
    replaying.set_defaults(func=_cmd_replay)

    holding_cli.add_parsers(tasks)
    lifecycle_cli.add_parsers(tasks)
    observe_cli.add_parser(tasks)
    inspect_cli.add_parser(tasks)
