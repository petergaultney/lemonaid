"""`lemonaid task create|assign|acknowledge`.

Anyone may assign a task. Messages go out only when this call committed the change: a
repeated request returns its first result, and its messages went out then.
"""

import argparse
import sys
import time
import typing as ty

from ..inbox import db
from . import cli_common
from .briefs import notices
from .model import holding, ids, ledger


def _cmd_create(args: argparse.Namespace) -> None:
    with db.connect() as conn:
        try:
            spec = cli_common.brief_id(conn, args.brief)
            holder = cli_common.brief_id(conn, args.assign)
            sponsor = cli_common.actor(conn)
            request_id = args.request_id or f"create:{time.time_ns()}"
            with ledger.transaction(conn):
                created = ledger.once(
                    conn,
                    request_id,
                    {
                        "op": "create",
                        "brief": spec,
                        "assign": holder,
                        "description": args.description,
                        "url": args.url,
                    },
                    lambda: holding.create(
                        conn,
                        description=args.description,
                        spec_brief_id=spec,
                        sponsor=sponsor if sponsor != "cli" else "",
                        holder_brief_id=holder,
                        subject_url_text=args.url,
                        checker_id="",
                        attached=False,
                        actor=sponsor,
                        request_id=request_id,
                        at=time.time(),
                    ),
                )
        except cli_common.Failed as error:
            cli_common.fail(args, str(error))
        except (ledger.RequestReused, ValueError) as error:
            cli_common.fail(args, str(error))
    cli_common.emit(args, created, f"task:{created['task_id']}")


def _cmd_assign(args: argparse.Namespace) -> None:
    with db.connect() as conn:
        try:
            if args.to.partition(":")[0] in ids.HOLDER_KINDS:
                raise cli_common.Failed(
                    "task assign takes a brief; human and external holders need an accountable"
                    " brief and a recheck date, which it can't record yet"
                )

            task = cli_common.task_id(args.task)
            to = cli_common.brief_id(conn, args.to)
            actor = cli_common.actor(conn)
            running = cli_common.running(conn, to)
            committed: list[bool] = []

            def run(expected: int, request_id: str, at: float) -> dict[str, ty.Any]:
                committed.append(True)
                return holding.assign(
                    conn,
                    task,
                    expected,
                    f"brief:{to}",
                    args.reason,
                    running,
                    actor,
                    request_id,
                    at,
                    delivery="message" if running else "",
                )

            assigned = cli_common.write(
                conn,
                args,
                {"op": "assign", "task_id": task, "to": to, "reason": args.reason},
                run,
            )
        except cli_common.Failed as error:
            cli_common.fail(args, str(error))

        said = (
            [
                notices.notice(conn, assigned, f"brief:{to}", actor),
                notices.tell_holder(ledger.state(conn, task), f"brief:{to}", actor, args.reason)
                if running and to != actor
                else "",
            ]
            if committed  # a repeated request's messages went out the first time
            else []
        )
    for line in filter(None, said):
        if not args.json:
            print(line, file=sys.stderr)
    shown = {**assigned, "notice": "\n".join(filter(None, said))}
    cli_common.emit(args, shown, f"task:{task} now held by brief:{to}")


def _cmd_acknowledge(args: argparse.Namespace) -> None:
    with db.connect() as conn:
        try:
            task = cli_common.task_id(args.task)
            me = cli_common.brief_id(conn, "self")
            done = cli_common.write(
                conn,
                args,
                {"op": "acknowledge", "task_id": task, "by": me},
                lambda expected, request_id, at: holding.acknowledge(
                    conn, task, expected, me, request_id, at
                ),
            )
        except cli_common.Failed as error:
            cli_common.fail(args, str(error))
    cli_common.emit(args, done, f"task:{task} acknowledged ({done['acknowledged']})")


def add_parsers(tasks: argparse._SubParsersAction) -> None:
    create = tasks.add_parser("create", help="A task for a brief that has none, or another one")
    create.add_argument("--brief", required=True, help="The brief specifying the work")
    create.add_argument("--assign", required=True, metavar="BRIEF", help="Its holder")
    create.add_argument("--description", required=True, help="One short line")
    create.add_argument("--url", default="", help="Its subject, if one exists yet")
    create.add_argument("--request-id", default="", help="Repeat a request safely")
    create.add_argument("--json", action="store_true", help="Print the result as JSON")
    create.set_defaults(func=_cmd_create)

    assign = tasks.add_parser(
        "assign", help="Give a task to a new holder; taking one you don't hold tells its holder"
    )
    assign.add_argument("task", metavar="TASK_ID")
    assign.add_argument(
        "--to",
        required=True,
        help="The brief that holds it next: a Lemon-ID, brief name or path, or self",
    )
    assign.add_argument("--reason", required=True, help="Why it changes hands")
    cli_common.add_write_options(assign)
    assign.set_defaults(func=_cmd_assign)

    acknowledge = tasks.add_parser(
        "acknowledge", help="Accept the task you were just assigned, after reading it"
    )
    acknowledge.add_argument("task", metavar="TASK_ID")
    cli_common.add_write_options(acknowledge)
    acknowledge.set_defaults(func=_cmd_acknowledge)
