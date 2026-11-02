"""`brief new` task options: which disposition the new brief gets, and recording it."""

import argparse
import json
import sqlite3
import sys
import time
import typing as ty
from collections import abc
from pathlib import Path

from ... import brief
from ...lineage import links
from ..model import ids, ledger
from . import notices, planning, registration

# Each option's unset value.
DEFAULTS: ty.Mapping[str, ty.Any] = {
    "new_task": False,
    "task": "",
    "observe": False,
    "no_task": "",
    "for_task": "",
    "independent": False,
    "task_url": "",
}


class Unregistered(Exception):
    """The brief exists but its task disposition wasn't recorded; `brief task ensure` repairs it."""

    def __init__(self, path: Path, lemon_id: str, cause: str, repair: str) -> None:
        super().__init__(
            f"{path} was created, but its task wasn't recorded: {cause}."
            f" Run `lemonaid brief task ensure {lemon_id} {repair}` to repair it."
        )
        self.path = path
        self.lemon_id = lemon_id


def _mode(args: argparse.Namespace) -> str:
    chosen = [
        name
        for name, given in (
            ("new", args.new_task),
            ("task", bool(args.task)),
            ("exempt", bool(args.no_task)),
        )
        if given
    ]
    if len(chosen) > 1:
        raise ledger.Refused("--new-task, --task and --no-task exclude each other")

    if args.observe and not args.task:
        raise ledger.Refused("--observe needs --task")

    if (args.for_task or args.independent) and chosen and chosen[0] != "new":
        raise ledger.Refused("--for-task and --independent go with a new task")

    if args.for_task and args.independent:
        raise ledger.Refused("--for-task and --independent exclude each other")

    if chosen and chosen[0] == "task":
        return "observe" if args.observe else "task"

    return chosen[0] if chosen else "new"


def caller(conn: sqlite3.Connection) -> str:
    """The Lemon-ID of whoever runs the command, or "" when it has no brief."""
    try:
        return brief.lemon.own_id(conn)
    except (LookupError, ValueError, brief.store.ChangedUnderneath):
        return ""


def conflict(args: argparse.Namespace, existing: ty.Mapping[str, ty.Any]) -> str:
    """Why the requested options disagree with the brief's recorded disposition; "" if not."""
    requested = _mode(args)
    recorded = existing["disposition"]
    if requested == "exempt":
        same = recorded == "exempt"
    elif requested == "new":
        same = recorded == "holds"
    else:
        wanted = ids.task_id(args.task)
        same = existing.get("task_id") == wanted and recorded == (
            "observe" if requested == "observe" else "holds"
        )
    if same:
        return ""

    match recorded:
        case "holds":
            return (
                f"the brief already holds task:{existing['task_id']}; to follow another task"
                " instead, run `lemonaid task observe TASK_ID`"
                f" (add `--instead-of {existing['task_id']}` if yours duplicates it)"
            )
        case "observe":
            return f"the brief already observes task:{existing['task_id']}"
    return f"the brief is already exempt: {existing.get('reason', '')}"


def given(args: argparse.Namespace) -> bool:
    return any(getattr(args, name) != unset for name, unset in DEFAULTS.items())


def _covering(conn: sqlite3.Connection, url: str) -> str:
    """An open task about *url*, or ""."""
    row = (
        url
        and conn.execute(
            "SELECT task_id FROM tasks WHERE subject_url = ? AND lifecycle != 'closed'"
            " ORDER BY created_at LIMIT 1",
            (url,),
        ).fetchone()
    )
    return row["task_id"] if row else ""


def plan(
    conn: sqlite3.Connection,
    args: argparse.Namespace,
    *,
    sponsor: str,
    actor: str,
    enabled: bool,
    template: str,
    existing_task_templates: abc.Collection[str],
    attached: bool,
    subject_url: str = "",
) -> planning.Plan | None:
    """The disposition to record, or None with task support off. Raises ledger.Refused.

    A template in *existing_task_templates* (a review, normally) takes the work's task, and
    makes a task of its own only when asked to and no open task is about *subject_url*: a
    teammate's PR, say, that no lemon's task covers.
    """
    if not enabled:
        if given(args):
            raise ledger.Refused("task options need `[tasks] enabled = true` in config")

        return None

    if template in existing_task_templates and not args.task:
        covering = _covering(conn, subject_url)
        if covering or not args.new_task:
            raise ledger.Refused(
                f"the {template} template takes the work's existing task"
                + (f", task:{covering}" if covering else "")
                + ": pass --task TASK_ID, with --observe to leave its holder alone"
                + ("" if covering else ", or --new-task when no lemon's task covers the work")
            )

    try:
        task = ids.task_id(args.task) if args.task else ""
        parent = ids.task_id(args.for_task) if args.for_task else ""
    except ValueError as error:
        raise ledger.Refused(f"not a task ID: {error}") from None
    planned = planning.plan(
        conn, _mode(args), task, args.no_task, sponsor, actor, parent, args.independent, attached
    )
    if planned.mode != "new":
        return planned

    if template in existing_task_templates:
        return planned._replace(subject_url=subject_url)  # so a second review finds it

    return planned._replace(subject_url=args.task_url)


def attached_plan(
    conn: sqlite3.Connection, args: argparse.Namespace, enabled: bool
) -> planning.Plan | None:
    """The plan for a brief attached as it is created; it blocks no task of the caller's
    unless --for-task says so. The caller sets `attached` once it knows whether a lemon
    took the brief or a window is still waiting for one."""
    return plan(
        conn,
        args,
        sponsor="",
        actor=caller(conn),
        enabled=enabled,
        template="",
        existing_task_templates=(),
        attached=False,
    )


def register(
    conn: sqlite3.Connection,
    planned: planning.Plan,
    path: Path,
    lemon_id: str,
    sponsor: str,
    title: str,
    link_parent: bool,
) -> dict[str, ty.Any]:
    """Record the planned disposition; raises Unregistered, keeping the brief file.

    Also links the brief to its parent now rather than when its lemon starts, so the
    parent's `task list --tree` shows the task while the child waits to launch.
    """
    try:
        if link_parent and sponsor and not links.parent_of(conn, lemon_id):
            links.set_parent(conn, lemon_id, sponsor)
        recorded = registration.register(conn, planned, lemon_id, sponsor, title, time.time())
    except (ledger.Refused, links.LinkError, sqlite3.Error, LookupError) as error:
        raise Unregistered(path, lemon_id, str(error), planning.repair_flags(planned)) from None
    if said := notices.notice(conn, recorded, planned.actor):
        print(said, file=sys.stderr)
        return {**recorded, "notice": said}

    return recorded


def report(problem: Unregistered, as_json: bool) -> None:
    if as_json:
        print(
            json.dumps(
                {"path": str(problem.path), "lemon_id": problem.lemon_id, "error": str(problem)},
                ensure_ascii=False,
            )
        )
    else:
        print(problem, file=sys.stderr)


def add_arguments(parser: argparse.ArgumentParser) -> None:
    group = parser.add_argument_group("tasks", "with [tasks] enabled: the new brief's task")
    group.add_argument("--new-task", action="store_true", help="A new task it holds (the default)")
    group.add_argument(
        "--task",
        default="",
        metavar="TASK_ID",
        help="Hand it an existing task; taking one you don't hold tells its holder",
    )
    group.add_argument(
        "--observe", action="store_true", help="With --task: link it without taking the task"
    )
    group.add_argument(
        "--no-task", default="", metavar="REASON", help="A standing role's exemption"
    )
    group.add_argument(
        "--for-task",
        default="",
        metavar="TASK_ID",
        help="The task of yours that waits for this one",
    )
    group.add_argument(
        "--independent", action="store_true", help="This work doesn't block any task of yours"
    )
    group.add_argument("--task-url", default="", metavar="URL", help="A new task's subject URL")
