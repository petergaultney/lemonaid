"""`lemonaid task recheck --all | BRIEF...`: ask lemons to re-check their Status.

lemonaid only records the request on each open task the briefs hold. The checker sees it on
its next pass and decides whom to ask and in what words.
"""

import argparse
import sqlite3
import time
import uuid

from ..inbox import db
from . import cli_common
from .model import holding, ledger, lifecycle


def _held(conn: sqlite3.Connection, names: list[str]) -> tuple[list[str], list[str]]:
    """The open tasks *names* hold, every brief-held one when *names* is empty, and the
    briefs among *names* that hold none."""
    if not names:
        return [
            row["task_id"]
            for row in conn.execute(
                "SELECT task_id FROM tasks WHERE lifecycle != 'closed' AND holder LIKE 'brief:%'"
                " ORDER BY created_at"
            )
        ], []

    found, idle = [], []
    for name in names:
        held = holding.held_by(conn, cli_common.brief_id(conn, name))
        found += [t["task_id"] for t in held]
        idle += [] if held else [name]
    return list(dict.fromkeys(found)), idle


def _cmd_recheck(args: argparse.Namespace) -> None:
    if bool(args.all) == bool(args.briefs):
        cli_common.fail(args, "name briefs to re-check, or pass --all")

    with db.connect() as conn:
        try:
            tasks, without = _held(conn, args.briefs)
        except cli_common.Failed as error:
            cli_common.fail(args, str(error))
        actor = cli_common.actor(conn)
        requested = []
        for task in tasks:
            with ledger.transaction(conn):
                state = ledger.state(conn, task)
                assert state is not None
                requested.append(
                    lifecycle.request_recheck(
                        conn, task, state["revision"], actor, str(uuid.uuid4()), time.time()
                    )
                )
    cli_common.emit(
        args,
        {"requested": requested, "hold_no_task": without},
        "\n".join(
            [
                *(f"re-check requested on task:{r['task_id']} ({r['holder']})" for r in requested),
                *(f"{name} holds no open task" for name in without),
            ]
        )
        or "no open task to re-check",
    )


def add_parser(tasks: argparse._SubParsersAction) -> None:
    parser = tasks.add_parser(
        "recheck",
        help="Ask lemons to re-check their Status, through the checker",
        description="Records a re-check request on each open task the briefs hold; the"
        " checker decides on its next pass whom to ask and what to say.",
    )
    parser.add_argument("briefs", nargs="*", metavar="BRIEF", help="A brief, Lemon-ID or `self`")
    parser.add_argument("--all", action="store_true", help="Every open task a brief holds")
    parser.add_argument("--json", action="store_true", help="Print the result as JSON")
    parser.set_defaults(func=_cmd_recheck)
