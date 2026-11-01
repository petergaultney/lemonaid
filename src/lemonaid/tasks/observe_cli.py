"""`lemonaid task observe|unobserve`: follow a task another brief holds, or stop.

A lemon that took or created its own task for work another task already covers observes
that one instead; `--instead-of` closes its own as a duplicate in the same transaction.
A lemon that hands a task on observes it already, until it runs `unobserve`.
"""

import argparse
import sqlite3
import time
import typing as ty

from ..inbox import db
from . import cli_common
from .model import associations, ledger, lifecycle


def _observe(
    conn: sqlite3.Connection, task: str, own: str, me: str, request_id: str
) -> dict[str, ty.Any]:
    at = time.time()
    if own:
        state = ledger.state(conn, own)
        if state is None or state["holder"] != f"brief:{me}" or state["lifecycle"] == "closed":
            raise cli_common.Failed(f"task:{own} isn't an open task you hold")

        lifecycle.close(
            conn,
            own,
            state["revision"],
            f"duplicate of task:{task}, which it now observes",
            me,
            request_id,
            at,
        )
    current = ledger.state(conn, task)
    if current is None:
        raise cli_common.Failed(f"no task:{task}")

    revision = associations.observe(conn, task, current["revision"], me, me, request_id, at)
    return {"task_id": task, "revision": revision, "closed": own, "holder": current["holder"]}


def _cmd_observe(args: argparse.Namespace) -> None:
    with db.connect() as conn:
        try:
            task = cli_common.task_id(args.task)
            own = cli_common.task_id(args.instead_of) if args.instead_of else ""
            if own == task:
                raise cli_common.Failed(f"task:{task} can't be a duplicate of itself")
            me = cli_common.brief_id(conn, "self")
            request_id = args.request_id or f"observe:{me}:{task}:{own}"
            operation = {"op": "observe", "task_id": task, "by": me, "instead_of": own}
            with ledger.transaction(conn):
                done = ledger.once(
                    conn, request_id, operation, lambda: _observe(conn, task, own, me, request_id)
                )
        except cli_common.Failed as error:
            cli_common.fail(args, str(error))
        except (ledger.Conflict, ledger.RequestReused, ValueError) as error:
            cli_common.fail(args, str(error))
    closed = f"; task:{own} closed as its duplicate" if own else ""
    cli_common.emit(args, done, f"observing task:{task}, held by {done['holder']}{closed}")


def _cmd_unobserve(args: argparse.Namespace) -> None:
    with db.connect() as conn:
        try:
            task = cli_common.task_id(args.task)
            me = cli_common.brief_id(conn, "self")
            done = cli_common.write(
                conn,
                args,
                {"op": "unobserve", "task_id": task, "by": me},
                lambda expected, request_id, at: {
                    "task_id": task,
                    "revision": associations.unobserve(
                        conn, task, expected, me, me, request_id, at
                    ),
                },
            )
        except cli_common.Failed as error:
            cli_common.fail(args, str(error))
    cli_common.emit(args, done, f"no longer observing task:{task}")


def add_parser(tasks: argparse._SubParsersAction) -> None:
    observe = tasks.add_parser(
        "observe", help="Follow a task another brief holds; --instead-of retires your duplicate"
    )
    observe.add_argument("task", metavar="TASK_ID")
    observe.add_argument(
        "--instead-of",
        default="",
        metavar="OWN_TASK_ID",
        help="Close this task you hold as a duplicate of TASK_ID",
    )
    observe.add_argument("--request-id", default="", help="Repeat a request safely")
    observe.add_argument("--json", action="store_true", help="Print the result as JSON")
    observe.set_defaults(func=_cmd_observe)

    unobserve = tasks.add_parser("unobserve", help="Stop following a task you observe")
    unobserve.add_argument("task", metavar="TASK_ID")
    cli_common.add_write_options(unobserve)
    unobserve.set_defaults(func=_cmd_unobserve)
