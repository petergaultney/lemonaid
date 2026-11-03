"""`lemonaid task create|assign`.

Anyone may assign a task. Messages go out only when this call committed the change: a
repeated request returns its first result, and its messages went out then.
"""

import argparse
import time
import typing as ty

from ..inbox import db
from . import cli_common
from .briefs import liveness, notices, subject_hints
from .model import holding, ledger


def _cmd_create(args: argparse.Namespace) -> None:
    with db.connect() as conn:
        try:
            spec = cli_common.brief_id(conn, args.brief)
            holder = cli_common.brief_id(conn, args.assign)
            sponsor = cli_common.actor(conn)
            request_id = args.request_id or f"create:{time.time_ns()}"
            committed: list[bool] = []

            def make() -> dict[str, ty.Any]:
                if not liveness.live(conn, holder):  # a retry returns its first result instead
                    raise cli_common.Failed(liveness.refusal(holder))

                committed.append(True)
                return holding.create(
                    conn,
                    description=args.description,
                    spec_brief_id=spec,
                    sponsor=sponsor if sponsor != "cli" else "",
                    holder_brief_id=holder,
                    subject_url_text=args.url,
                    checker_id="",
                    attached=True,
                    actor=sponsor,
                    request_id=request_id,
                    at=time.time(),
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
            notices.tell_holder(state, sponsor, "a new task")
            if committed and holder != sponsor
            else "",
            subject_hints.unwatched(conn, state["holder"], state["subject_url"])
            if state["subject_url"]
            else "",
        ]
    cli_common.report(args, created, said, f"task:{created['task_id']}")


def _cmd_assign(args: argparse.Namespace) -> None:
    with db.connect() as conn:
        try:
            task = cli_common.task_id(args.task)
            brief_id = cli_common.brief_id(conn, args.to)
            to = f"brief:{brief_id}"
            actor = cli_common.actor(conn)

            def assign(expected: int, request_id: str, at: float) -> dict[str, ty.Any]:
                if not liveness.live(conn, brief_id):  # a retry returns its first result instead
                    raise cli_common.Failed(liveness.refusal(brief_id))

                return holding.assign(
                    conn, task, expected, to, args.reason, True, actor, request_id, at
                )

            assigned, committed = cli_common.write_once(
                conn,
                args,
                {
                    "op": "assign",
                    "task_id": task,
                    "to": to,
                    "reason": args.reason,
                },
                assign,
            )
        except cli_common.Failed as error:
            cli_common.fail(args, str(error))
        state = ledger.state(conn, task)
        assert state is not None
        said = [
            notices.notice(conn, {**assigned, "tell_holder": brief_id != actor}, actor, args.reason)
            if committed
            else "",
        ]
    cli_common.report(args, assigned, said, f"task:{task} now held by {to}")


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
        help="A brief (Lemon-ID, name, path or self); a person's turn is a brief's Status",
    )
    assign.add_argument("--reason", required=True, help="Why it changes hands")
    cli_common.add_write_options(assign)
    assign.set_defaults(func=_cmd_assign)
