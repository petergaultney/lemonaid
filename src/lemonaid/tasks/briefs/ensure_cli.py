"""`lemonaid brief task ensure`: record a brief's task disposition if it has none."""

import argparse
import sys
import time

from ...brief import lemon
from ...inbox import db
from ...lineage import links
from .. import cli_common
from ..model import ledger
from . import notices, options_cli, registration


def _title(text: str) -> str:
    return next((ln[2:].strip() for ln in text.splitlines() if ln.startswith("# ")), "")


def _cmd_ensure(args: argparse.Namespace) -> None:
    with db.connect() as conn:
        try:
            brief_id = cli_common.brief_id(conn, args.brief)
            path = lemon.brief_of(conn, brief_id)
            title = _title(path.read_text()) if path else ""
            sponsor = links.parent_of(conn, brief_id)
            if existing := registration.disposition(conn, brief_id):
                if problem := options_cli.conflict(args, existing):
                    raise ledger.Refused(problem)

                found = {**existing, "created": False}
            else:
                live = notices.running(conn, brief_id)
                actor = options_cli.caller(conn)
                planned = options_cli.plan(
                    conn,
                    args,
                    sponsor=sponsor,
                    actor=actor,
                    enabled=True,
                    template="",
                    existing_task_templates=(),
                    attached=live,
                )
                assert planned is not None
                found = registration.ensure(
                    conn, planned, brief_id, sponsor, title or brief_id, time.time()
                )
                if said := notices.notice(conn, found, actor):
                    print(said, file=sys.stderr)
        except cli_common.Failed as error:
            cli_common.fail(args, str(error))
        except (ValueError, ledger.RequestReused, OSError) as error:
            cli_common.fail(args, str(error))
    shown = f"task:{found['task_id']}" if "task_id" in found else f"exempt: {found.get('reason')}"
    cli_common.emit(args, {"lemon_id": brief_id, **found}, shown)


def add_parser(brief_subparsers: argparse._SubParsersAction) -> None:
    parser = brief_subparsers.add_parser("task", help="A brief's task disposition")
    verbs = parser.add_subparsers(dest="brief_task_command", required=True)
    ensure = verbs.add_parser(
        "ensure",
        help="Record BRIEF's task disposition unless it has one; with no options, a new task",
    )
    ensure.add_argument("brief", metavar="BRIEF", help="A Lemon-ID, brief name or path, or self")
    options_cli.add_arguments(ensure)
    ensure.add_argument("--json", action="store_true", help="Print the result as JSON")
    ensure.set_defaults(func=_cmd_ensure)
