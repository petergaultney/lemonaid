"""`lemonaid task set-url|depend|result|close|reopen`.

Messages go out only when this call committed the change: a repeated request returns its
first result, and its messages went out then.
"""

import argparse
import typing as ty

from ..inbox import db
from . import cli_common
from .briefs import notices, subject_hints
from .model import dependencies, ledger, lifecycle


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
        state = ledger.state(conn, task)
        assert state is not None
        url = state["subject_url"]
        hint = subject_hints.unwatched(conn, state["holder"], url) if url else ""
    cli_common.report(args, changed, [hint], f"task:{task} now at {url or 'no URL'}")


def _cmd_depend(args: argparse.Namespace) -> None:
    with db.connect() as conn:
        try:
            task = cli_common.task_id(args.task)
            other = cli_common.task_id(args.on)
            actor = cli_common.actor(conn)
            waits = cli_common.write(
                conn,
                args,
                {"op": "depend", "task_id": task, "on": other},
                lambda expected, request_id, at: {
                    "task_id": task,
                    "on": other,
                    "revision": dependencies.depend(
                        conn, task, expected, other, actor, request_id, at
                    ),
                },
            )
        except cli_common.Failed as error:
            cli_common.fail(args, str(error))
    cli_common.emit(args, waits, f"task:{task} waits for task:{other}")


def _cmd_result(args: argparse.Namespace) -> None:
    with db.connect() as conn:
        try:
            task = cli_common.task_id(args.task)
            actor = cli_common.actor(conn)
            recorded = cli_common.write(
                conn,
                args,
                {"op": "result", "task_id": task, "evidence": args.evidence},
                lambda expected, request_id, at: lifecycle.result(
                    conn, task, expected, args.evidence, actor, request_id, at
                ),
            )
        except cli_common.Failed as error:
            cli_common.fail(args, str(error))
    cli_common.emit(args, recorded, f"task:{task} result: {args.evidence}")


def _not_mine(state: ty.Mapping[str, ty.Any], actor: str) -> bool:
    return state["holder"] != f"brief:{actor}"


def _cmd_close(args: argparse.Namespace) -> None:
    with db.connect() as conn:
        try:
            task = cli_common.task_id(args.task)
            actor = cli_common.actor(conn)

            def close(expected: int, request_id: str, at: float) -> dict[str, ty.Any]:
                return lifecycle.close(conn, task, expected, args.reason, actor, request_id, at)

            closed, committed = cli_common.write_once(
                conn, args, {"op": "close", "task_id": task, "reason": args.reason}, close
            )
        except cli_common.Failed as error:
            cli_common.fail(args, str(error))
        state = ledger.state(conn, task)
        assert state is not None
        parents = [ledger.state(conn, p) for p in closed["released"]] if committed else []
        said = [
            notices.tell_closed(state, actor, args.reason)
            if committed and _not_mine(state, actor)
            else "",
            *(
                notices.tell_released(parent, state, actor, args.reason)
                for parent in parents
                if parent is not None and _not_mine(parent, actor)
            ),
        ]
    cli_common.report(args, closed, said, f"task:{task} closed")


def _cmd_reopen(args: argparse.Namespace) -> None:
    with db.connect() as conn:
        try:
            task = cli_common.task_id(args.task)
            actor = cli_common.actor(conn)
            reopened, committed = cli_common.write_once(
                conn,
                args,
                {"op": "reopen", "task_id": task, "reason": args.reason},
                lambda expected, request_id, at: lifecycle.reopen(
                    conn, task, expected, args.reason, actor, request_id, at
                ),
            )
        except cli_common.Failed as error:
            cli_common.fail(args, str(error))
        state = ledger.state(conn, task)
        assert state is not None
        said = [
            notices.tell_closed(state, actor, args.reason)
            if committed and _not_mine(state, actor)
            else ""
        ]
    cli_common.report(args, reopened, said, f"task:{task} reopened, held by {state['holder']}")


def add_parsers(tasks: argparse._SubParsersAction) -> None:
    set_url = tasks.add_parser("set-url", help="Replace a task's subject URL, keeping its ID")
    set_url.add_argument("task", metavar="TASK_ID")
    set_url.add_argument("url", metavar="URL", help="The new URL, or '' to clear it")
    set_url.add_argument("--reason", required=True, help="Why it changed, such as a successor PR")
    cli_common.add_write_options(set_url)
    set_url.set_defaults(func=_cmd_set_url)

    depend = tasks.add_parser(
        "depend", help="Make a task wait for another, so its holder isn't idle while that one moves"
    )
    depend.add_argument("task", metavar="TASK_ID")
    depend.add_argument(
        "--on", required=True, metavar="OTHER_TASK_ID", help="The task it waits for"
    )
    cli_common.add_write_options(depend)
    depend.set_defaults(func=_cmd_depend)

    result = tasks.add_parser("result", help="Record a result without closing the task")
    result.add_argument("task", metavar="TASK_ID")
    result.add_argument(
        "--evidence", required=True, help="Where the result is: a commit, PR, document or brief"
    )
    cli_common.add_write_options(result)
    result.set_defaults(func=_cmd_result)

    close = tasks.add_parser("close", help="Close a task, releasing tasks that wait for it")
    close.add_argument("task", metavar="TASK_ID")
    close.add_argument(
        "--reason", required=True, help="Why it's finished, naming where the result is"
    )
    cli_common.add_write_options(close)
    close.set_defaults(func=_cmd_close)

    reopen = tasks.add_parser("reopen", help="Reopen a closed task with its last holder")
    reopen.add_argument("task", metavar="TASK_ID")
    reopen.add_argument("--reason", required=True, help="Why it isn't finished")
    cli_common.add_write_options(reopen)
    reopen.set_defaults(func=_cmd_reopen)
