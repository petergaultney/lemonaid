"""`brief attach`, `new`, `detach`, `list`: briefs attached to lemon sessions.

The edits to a brief's contents are in `verbs_cli`."""

import argparse
import datetime
import sqlite3
from pathlib import Path

from .. import home
from ..inbox import db
from . import (
    attached,
    check_cli,
    child_cli,
    command,
    identity,
    query_cli,
    selector,
    store,
    verbs_cli,
)


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
        conn,
        chosen.tmux_session,
        chosen.tmux_window,
        path,
        attached.live_channels(conn),
        chosen.tmux_window_id,
    )
    return (
        {"path": str(path), "lemon_id": lemon_id, "channel": None, "pending": window},
        "",
        f"{path} -> the next lemon to start in {window}",
    )


def _cmd_attach(args: argparse.Namespace) -> None:
    path = store.resolve(args.file)
    if error := store.outside_error(path):
        command.finish(args, {}, error)

    if not path.is_file():
        command.finish(args, {}, f"No brief at {path}")

    with db.connect() as conn:
        result, error, message = _attach(conn, args, path)
    command.finish(args, result, error, message)


def _cmd_new(args: argparse.Namespace) -> None:
    targets = args.use_self or args.session or args.channel or args.id is not None
    if args.child and targets:
        command.finish(
            args, {}, "--child attaches the brief to no one; name its parent with --parent"
        )

    if args.child:
        child_cli.cmd(args)
        return

    if stray := child_cli.given(args):
        command.finish(
            args, {}, f"{', '.join(stray)} {'needs' if len(stray) == 1 else 'need'} --child"
        )

    if not targets:
        command.finish(
            args, {}, "Name the lemon to attach it to (--self, --session, --channel, --id)"
        )

    if paused := home.layout.paused():
        command.finish(args, {}, paused)

    try:
        path = store.create(args.title, datetime.date.today())
    except FileExistsError as e:
        command.finish(args, {}, f"{e.filename} already exists; attach it instead")
        return

    try:
        with db.connect() as conn:
            identity.ensure(conn, path, regenerate_on_collision=True)
    except BaseException:
        path.unlink(missing_ok=True)
        raise

    with db.connect() as conn:
        result, error, message = _attach(conn, args, path)
    command.finish(args, {"path": str(path), **result}, error, message or str(path))


def _cmd_detach(args: argparse.Namespace) -> None:
    with db.connect() as conn:
        chosen, error = selector.select(conn, args)
        path = attached.detach(conn, chosen.channel) if chosen and chosen.channel else None
    command.finish(
        args,
        {"path": str(path) if path else None, "detached": path is not None},
        error,
        f"detached {path}" if path else "no brief was attached",
    )


def add_parsers(brief_subparsers: argparse._SubParsersAction) -> None:
    own_id = command.parser(
        brief_subparsers, "id", "Print the stable ID stored with a lemon's brief"
    )
    own_id.add_argument(
        "--reroll",
        action="store_true",
        help="Replace the ID's WordyBin with a random unused one; the old ID keeps working",
    )
    own_id.add_argument(
        "--set",
        default="",
        metavar="WORDYBIN",
        help="Reroll to this two-word WordyBin (e.g. QuickOdd) instead of a random one",
    )
    own_id.set_defaults(func=query_cli.cmd_id)

    attach = command.parser(brief_subparsers, "attach", "Attach a brief file to one lemon session")
    attach.add_argument("file", help="A path, or a name inside ~/.lemons/brief/ (.md optional)")
    attach.set_defaults(func=_cmd_attach)

    new = command.parser(
        brief_subparsers,
        "new",
        "Create a dated brief in ~/.lemons/brief/ and attach it, or with --child leave it unattached",
        target_required=False,
    )
    new.add_argument("title", help="The task; the file is named <date>-<slug of title>.md")
    child_cli.add_arguments(new)
    new.set_defaults(func=_cmd_new)

    verbs_cli.add_parsers(brief_subparsers)
    check_cli.add_parsers(brief_subparsers)

    detach = command.parser(brief_subparsers, "detach", "Detach a lemon's brief; the file stays")
    detach.set_defaults(func=_cmd_detach)

    listing = command.parser(
        brief_subparsers,
        "list",
        "Every attached brief and its session, and briefs waiting for a lemon to start",
        with_target=False,
    )
    listing.set_defaults(func=query_cli.cmd_list)
