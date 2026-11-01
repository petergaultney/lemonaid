"""What the task commands share: naming briefs, failing, request IDs and conditional writes."""

import argparse
import json
import sqlite3
import sys
import time
import typing as ty
import uuid
from collections import abc

from .. import brief
from .model import identities, ids, ledger


class Failed(Exception):
    pass


def fail(args: argparse.Namespace, error: str, **extra: ty.Any) -> ty.NoReturn:
    if getattr(args, "json", False):
        print(json.dumps({"error": error, **extra}, ensure_ascii=False))
    else:
        print(error, file=sys.stderr)
    raise SystemExit(1)


def emit(args: argparse.Namespace, result: ty.Mapping[str, ty.Any], text: str) -> None:
    if getattr(args, "json", False):
        print(json.dumps({**result, "error": None}, ensure_ascii=False, default=str))
    else:
        print(text)


def brief_id(conn: sqlite3.Connection, name: str, channel: str = "") -> str:
    """The current Lemon-ID *name* means; `self` is the caller. Raises Failed."""
    try:
        if name == "self":
            return brief.lemon.own_id(conn, channel)

        return identities.current(conn, brief.lemon.lemon_id(conn, name))
    except (LookupError, ValueError, brief.store.ChangedUnderneath) as error:
        raise Failed(f"{name}: {error}") from None


def actor(conn: sqlite3.Connection, channel: str = "") -> str:
    """The caller's Lemon-ID, or `cli` when it has no brief."""
    try:
        return brief.lemon.own_id(conn, channel)
    except (LookupError, ValueError, brief.store.ChangedUnderneath):
        return "cli"


def task_id(text: str) -> str:
    try:
        return ids.task_id(text)
    except ValueError:
        raise Failed(f"{text!r} is not a task ID") from None


def write(
    conn: sqlite3.Connection,
    args: argparse.Namespace,
    operation: ty.Mapping[str, ty.Any],
    run: abc.Callable[[int, str, float], dict[str, ty.Any]],
) -> dict[str, ty.Any]:
    """Run a conditional mutation once per request ID.

    *run* gets the expected revision, the request ID and the time. Without
    `--expect-revision` the current revision is read here, once, and left out of the
    request's fingerprint, so a retried request still matches its first attempt.
    """
    task = operation["task_id"]
    request_id = args.request_id or str(uuid.uuid4())
    pinned = args.expect_revision is not None
    try:
        with ledger.transaction(conn):
            current = ledger.state(conn, task)
            if current is None:
                raise Failed(f"no task:{task}")

            expected = args.expect_revision if pinned else current["revision"]
            fingerprint = {**operation, **({"expect_revision": expected} if pinned else {})}
            return ledger.once(
                conn, request_id, fingerprint, lambda: run(expected, request_id, time.time())
            )
    except ledger.Conflict as conflict:
        raise Failed(str(conflict)) from None
    except (ledger.RequestReused, ValueError) as error:
        raise Failed(str(error)) from None


def add_write_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--expect-revision",
        type=int,
        default=None,
        metavar="N",
        help="Refuse unless the task is still at revision N (default: its current one)",
    )
    parser.add_argument(
        "--request-id",
        default="",
        help="Repeat a request safely: a committed one returns its first result",
    )
    parser.add_argument("--json", action="store_true", help="Print the result as JSON")


def write_once(
    conn: sqlite3.Connection,
    args: argparse.Namespace,
    operation: ty.Mapping[str, ty.Any],
    run: abc.Callable[[int, str, float], dict[str, ty.Any]],
) -> tuple[dict[str, ty.Any], bool]:
    """`cli_common.write`'s result, and whether this call committed it."""
    committed: list[bool] = []

    def counted(expected: int, request_id: str, at: float) -> dict[str, ty.Any]:
        committed.append(True)
        return run(expected, request_id, at)

    return write(conn, args, operation, counted), bool(committed)


def report(args: argparse.Namespace, result: dict, said: abc.Iterable[str], text: str) -> None:
    lines = [line for line in said if line]
    if not args.json:
        for line in lines:
            print(line, file=sys.stderr)
    emit(args, {**result, "notice": "\n".join(lines)}, text)
