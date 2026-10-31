"""`lemonaid task create|assign|acknowledge`.

Anyone may assign a task. Messages go out only when this call committed the change: a
repeated request returns its first result, and its messages went out then.
"""

import argparse
import time

from ..inbox import db
from . import cli_common
from .model import holding, ledger


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


def add_parsers(tasks: argparse._SubParsersAction) -> None:
    create = tasks.add_parser("create", help="A task for a brief that has none, or another one")
    create.add_argument("--brief", required=True, help="The brief specifying the work")
    create.add_argument("--assign", required=True, metavar="BRIEF", help="Its holder")
    create.add_argument("--description", required=True, help="One short line")
    create.add_argument("--url", default="", help="Its subject, if one exists yet")
    create.add_argument("--request-id", default="", help="Repeat a request safely")
    create.add_argument("--json", action="store_true", help="Print the result as JSON")
    create.set_defaults(func=_cmd_create)
