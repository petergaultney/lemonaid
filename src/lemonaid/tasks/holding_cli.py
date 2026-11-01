"""`lemonaid task create|assign|acknowledge`.

Anyone may assign a task. Messages go out only when this call committed the change: a
repeated request returns its first result, and its messages went out then.
"""

import argparse
import sqlite3
import time
import typing as ty

from ..inbox import db
from . import cli_common
from .briefs import notices
from .checker import checker_input
from .model import holding, ids, ledger


def _cmd_create(args: argparse.Namespace) -> None:
    with db.connect() as conn:
        try:
            spec = cli_common.brief_id(conn, args.brief)
            holder = cli_common.brief_id(conn, args.assign)
            sponsor = cli_common.actor(conn)
            running = cli_common.running(conn, holder)
            request_id = args.request_id or f"create:{time.time_ns()}"
            committed: list[bool] = []

            def make() -> dict[str, ty.Any]:
                committed.append(True)
                return holding.create(
                    conn,
                    description=args.description,
                    spec_brief_id=spec,
                    sponsor=sponsor if sponsor != "cli" else "",
                    holder_brief_id=holder,
                    subject_url_text=args.url,
                    checker_id="",
                    attached=running,
                    actor=sponsor,
                    request_id=request_id,
                    at=time.time(),
                    delivery="message" if running else "",
                )

            operation = {
                "op": "create",
                "brief": spec,
                "assign": holder,
                "description": args.description,
                "url": args.url,
            }
            with ledger.transaction(conn):
                created = ledger.once(conn, request_id, operation, make)
        except cli_common.Failed as error:
            cli_common.fail(args, str(error))
        except (ledger.RequestReused, ValueError) as error:
            cli_common.fail(args, str(error))
        state = ledger.state(conn, created["task_id"])
        assert state is not None
        said = [
            notices.tell_holder(state, sponsor, "a new task", created["message_id"])
            if committed and running and holder != sponsor
            else ""
        ]
    cli_common.report(args, created, said, f"task:{created['task_id']}")


def _target(conn: sqlite3.Connection, args: argparse.Namespace) -> tuple[str, str, str]:
    """The new holder, its accountable brief and its recheck time. Raises Failed."""
    if args.to.partition(":")[0] not in ids.HOLDER_KINDS:
        if args.accountable or args.recheck_at:
            raise cli_common.Failed(
                "--accountable and --recheck-at are for human and external holders"
            )

        return f"brief:{cli_common.brief_id(conn, args.to)}", "", ""

    if args.recheck_at:
        try:
            checker_input.timestamp(args.recheck_at)
        except ValueError:
            raise cli_common.Failed(
                f"--recheck-at {args.recheck_at!r} is not an RFC 3339 time"
            ) from None

    accountable = cli_common.brief_id(conn, args.accountable) if args.accountable else ""
    try:
        return ids.holder(args.to), accountable, args.recheck_at
    except ValueError as error:
        raise cli_common.Failed(str(error)) from None


def _cmd_assign(args: argparse.Namespace) -> None:
    with db.connect() as conn:
        try:
            task = cli_common.task_id(args.task)
            to, accountable, recheck_at = _target(conn, args)
            actor = cli_common.actor(conn)
            brief_id = to.removeprefix("brief:") if to.startswith("brief:") else ""
            running = bool(brief_id) and cli_common.running(conn, brief_id)
            assigned, committed = cli_common.write_once(
                conn,
                args,
                {
                    "op": "assign",
                    "task_id": task,
                    "to": to,
                    "reason": args.reason,
                    "accountable": accountable,
                    "recheck_at": recheck_at,
                },
                lambda expected, request_id, at: holding.assign(
                    conn,
                    task,
                    expected,
                    to,
                    args.reason,
                    running,
                    actor,
                    request_id,
                    at,
                    delivery="message" if running else "",
                    accountable=accountable,
                    recheck_at=recheck_at,
                ),
            )
        except cli_common.Failed as error:
            cli_common.fail(args, str(error))
        state = ledger.state(conn, task)
        assert state is not None
        said = [
            notices.notice(conn, assigned, actor) if committed else "",
            notices.tell_holder(state, actor, args.reason, assigned["message_id"])
            if committed and running and brief_id != actor
            else "",
        ]
    cli_common.report(args, assigned, said, f"task:{task} now held by {to}")


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
        help="A brief (Lemon-ID, name, path or self), human:ID or external:ID",
    )
    assign.add_argument("--reason", required=True, help="Why it changes hands")
    assign.add_argument(
        "--accountable",
        default="",
        metavar="BRIEF",
        help="For a human or external holder: the brief that answers for it",
    )
    assign.add_argument(
        "--recheck-at",
        default="",
        metavar="TIME",
        help="For an external holder: when to look again, as RFC 3339",
    )
    cli_common.add_write_options(assign)
    assign.set_defaults(func=_cmd_assign)

    acknowledge = tasks.add_parser(
        "acknowledge", help="Accept the task you were just assigned, after reading it"
    )
    acknowledge.add_argument("task", metavar="TASK_ID")
    cli_common.add_write_options(acknowledge)
    acknowledge.set_defaults(func=_cmd_acknowledge)
