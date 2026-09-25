"""`brief attach`, `new`, `now`, `status`, `detach`, `list`: briefs attached to lemon sessions.

The edits go through lemonaid rather than the file so a sandboxed lemon (Codex
writes only inside its workspace) can keep its own brief current.
"""

import argparse
import datetime
import json
import sqlite3
import sys
from collections import abc
from pathlib import Path

from ..inbox import db
from . import attached, identity, query_cli, selector, store


def _finish(args: argparse.Namespace, result: dict, error: str, message: str = "") -> None:
    if args.json:
        print(json.dumps({**result, "error": error or None}, ensure_ascii=False))
    elif error:
        print(error, file=sys.stderr)
    elif message:
        print(message)

    if error:
        sys.exit(1)


def _attach(
    conn: sqlite3.Connection, args: argparse.Namespace, path: Path
) -> tuple[dict, str, str]:
    """(JSON result, error, message) for attaching *path* to the lemon *args* names."""
    chosen, error = selector.select(conn, args)
    if chosen is None:
        return {}, error, ""

    try:
        lemon_id = identity.ensure(conn, path)
    except (ValueError, store.ChangedUnderneath) as cause:
        return {}, str(cause), ""

    if chosen.channel:
        moved_from = attached.attach(conn, chosen.channel, path)
        return (
            {
                "path": str(path),
                "lemon_id": lemon_id,
                "channel": chosen.channel,
                "moved_from": moved_from or None,
            },
            "",
            f"{path} -> {chosen.channel}" + (f" (moved from {moved_from})" if moved_from else ""),
        )

    window = f"{chosen.tmux_session}:{chosen.tmux_window}"
    attached.attach_pending(
        conn, chosen.tmux_session, chosen.tmux_window, path, attached.newest_id(conn)
    )
    return (
        {"path": str(path), "lemon_id": lemon_id, "channel": None, "pending": window},
        "",
        f"{path} -> the next lemon to start in {window}",
    )


def _cmd_attach(args: argparse.Namespace) -> None:
    path = store.resolve(args.file)
    if error := store.outside_error(path):
        _finish(args, {}, error)

    if not path.is_file():
        _finish(args, {}, f"No brief at {path}")

    with db.connect() as conn:
        result, error, message = _attach(conn, args, path)
    _finish(args, result, error, message)


def _cmd_new(args: argparse.Namespace) -> None:
    try:
        path = store.create(args.title, datetime.date.today())
    except FileExistsError as e:
        _finish(args, {}, f"{e.filename} already exists; attach it instead")
        return

    try:
        with db.connect() as conn:
            identity.ensure(conn, path, regenerate_on_collision=True)
    except BaseException:
        path.unlink(missing_ok=True)
        raise

    with db.connect() as conn:
        result, error, message = _attach(conn, args, path)
    _finish(args, {"path": str(path), **result}, error, message or str(path))


def _own_brief(args: argparse.Namespace) -> tuple[Path | None, str]:
    with db.connect() as conn:
        chosen, error = selector.select(conn, args)
        if chosen is None:
            return None, error

        attached.claim_pending(conn)
        path = attached.by_channel(conn, [chosen.channel]).get(chosen.channel)

    if path is None:
        return None, "No brief attached; `lemonaid brief attach --self <file>` or `brief new`"

    if error := store.outside_error(path):
        return None, error

    if not path.is_file():
        return None, f"The attached brief {path} does not exist"

    return path, ""


def _edit(path: Path, change: abc.Callable[[str], str]) -> str:
    try:
        store.edit(path.resolve(), change)
    except store.ChangedUnderneath as e:
        return str(e)

    return ""


def _cmd_now(args: argparse.Namespace) -> None:
    path, error = _own_brief(args)
    if path:
        text = sys.stdin.read() if args.markdown == "-" else args.markdown
        error = _edit(path, lambda brief: store.with_now(brief, text))
    _finish(args, {"path": str(path) if path else None}, error, str(path))


def _cmd_status(args: argparse.Namespace) -> None:
    path, error = _own_brief(args)
    if path:
        error = _edit(path, lambda brief: store.with_status(brief, args.state))
    _finish(args, {"path": str(path) if path else None}, error, str(path))


def _cmd_detach(args: argparse.Namespace) -> None:
    with db.connect() as conn:
        chosen, error = selector.select(conn, args)
        path = attached.detach(conn, chosen.channel) if chosen and chosen.channel else None
    _finish(
        args,
        {"path": str(path) if path else None, "detached": path is not None},
        error,
        f"detached {path}" if path else "no brief was attached",
    )


def _parser(
    subparsers: argparse._SubParsersAction, name: str, summary: str, with_target: bool = True
) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(name, help=summary, description=summary)
    if with_target:
        selector.add_arguments(parser)
    parser.add_argument("--json", action="store_true", help="Print the result as JSON")
    return parser


def add_parsers(brief_subparsers: argparse._SubParsersAction) -> None:
    own_id = _parser(brief_subparsers, "id", "Print the stable ID stored with a lemon's brief")
    own_id.set_defaults(func=query_cli.cmd_id)

    attach = _parser(brief_subparsers, "attach", "Attach a brief file to one lemon session")
    attach.add_argument("file", help="A path, or a name inside ~/.brief-lemons/ (.md optional)")
    attach.set_defaults(func=_cmd_attach)

    new = _parser(brief_subparsers, "new", "Create a dated brief in ~/.brief-lemons/ and attach it")
    new.add_argument("title", help="The task; the file is named <date>-<slug of title>.md")
    new.set_defaults(func=_cmd_new)

    now = _parser(brief_subparsers, "now", "Replace the `## Now` section of a lemon's brief")
    now.add_argument("markdown", help="The new section body; - reads it from stdin")
    now.set_defaults(func=_cmd_now)

    status = _parser(brief_subparsers, "status", "Set the Status line of a lemon's brief")
    status.add_argument("state", choices=store.STATES)
    status.set_defaults(func=_cmd_status)

    detach = _parser(brief_subparsers, "detach", "Detach a lemon's brief; the file stays")
    detach.set_defaults(func=_cmd_detach)

    listing = _parser(
        brief_subparsers,
        "list",
        "Every attached brief and its session, and briefs waiting for a lemon to start",
        with_target=False,
    )
    listing.set_defaults(func=query_cli.cmd_list)
