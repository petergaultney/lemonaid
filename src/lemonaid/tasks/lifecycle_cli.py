"""`lemonaid task set-url|result|close|reopen`.

Messages go out only when this call committed the change: a repeated request returns its
first result, and its messages went out then.
"""

import argparse

from ..inbox import db
from . import cli_common
from .model import lifecycle


def _cmd_set_url(args: argparse.Namespace) -> None:
    with db.connect() as conn:
        try:
            task = cli_common.task_id(args.task)
            actor = cli_common.actor(conn)
            changed = cli_common.write(
                conn,
                args,
                {"op": "set-url", "task_id": task, "url": args.url, "reason": args.reason},
                lambda expected, request_id, at: lifecycle.set_url(
                    conn, task, expected, args.url, args.reason, actor, request_id, at
                ),
            )
        except cli_common.Failed as error:
            cli_common.fail(args, str(error))
    cli_common.emit(args, changed, f"task:{task} now at {args.url or 'no URL'}")


def add_parsers(tasks: argparse._SubParsersAction) -> None:
    set_url = tasks.add_parser("set-url", help="Replace a task's subject URL, keeping its ID")
    set_url.add_argument("task", metavar="TASK_ID")
    set_url.add_argument("url", metavar="URL", help="The new URL, or '' to clear it")
    set_url.add_argument("--reason", required=True, help="Why it changed, such as a successor PR")
    cli_common.add_write_options(set_url)
    set_url.set_defaults(func=_cmd_set_url)
