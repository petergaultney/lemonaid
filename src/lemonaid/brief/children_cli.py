"""`brief children`: a parent's children, their places and sessions, and what holds up cleanup."""

import argparse
import collections
import dataclasses
import json
import subprocess
import sys
import time
import typing as ty
from collections import abc

from ..config import load_config
from ..inbox import db
from ..log import get_logger
from ..places import ownership
from . import child_place, children, lemon, status, store

_log = get_logger("brief.children")

_TIMEOUT_SECONDS = 5


def _tmux_lines(*argv: str) -> list[str] | None:
    try:
        result = subprocess.run(
            ["tmux", *argv], capture_output=True, text=True, check=True, timeout=_TIMEOUT_SECONDS
        )
    except (OSError, subprocess.SubprocessError) as e:
        _log.warning("tmux %s failed: %s", argv[0], e)
        return None

    return result.stdout.splitlines()


def _world() -> child_place.World:
    sessions = _tmux_lines("list-sessions", "-F", "#{session_name}")
    clients = _tmux_lines("list-clients", "-F", "#{client_session}")
    config = load_config()
    return child_place.World(
        sessions=set(sessions) if sessions is not None else None,
        clients=collections.Counter(clients) if clients is not None else None,
        places=ownership.managed_places(config),
        panes=ownership.pane_paths(),
        roots=config.places.roots,
    )


def _fail(args: argparse.Namespace, error: str) -> ty.NoReturn:
    if args.json:
        print(json.dumps({"error": error}))
    else:
        print(error, file=sys.stderr)
    raise SystemExit(1)


def _session_line(child: children.Child) -> str:
    if not child.tmux_session:
        return "none yet"

    alive = {True: "alive", False: "gone", None: "unknown"}[child.alive]
    clients = "" if child.clients is None or not child.alive else f", {child.clients} attached"
    return f"{child.tmux_session} ({alive}{clients})"


def _lines(child: children.Child, now: float, indent: str) -> abc.Iterator[str]:
    held_for = status.age(now - child.since).removesuffix(" ago")
    held = (
        f"{child.status or '-'} "
        + ("since just now" if held_for == "just now" else f"for {held_for}")
        + f", updated {status.age(now - child.updated)}"
        if child.updated
        else f"{child.status or '-'}, no brief"
    )
    yield f"{indent}{child.lemon_id}  {held}  {child.name}"
    more = indent + "    "
    place = child.place
    yield f"{more}place    " + (
        f"{place.key}  {place.dir}"
        + ("" if place.exists else "  (gone)")
        + ("" if place.listed else "  (unlisted)")
        if place
        else "-"
    )
    yield f"{more}session  {_session_line(child)}"
    if child.prs:
        yield f"{more}PRs      {'  '.join(child.prs)}"
    reasons = f": {', '.join(child.held_by)}" if child.held_by else ""
    yield f"{more}cleanup  {child.cleanup}{reasons}"
    for grandchild in child.children:
        yield from _lines(grandchild, now, more)


def _as_json(child: children.Child) -> dict:
    return {
        **dataclasses.asdict(child),
        "children": [_as_json(c) for c in child.children],
    }


def cmd(args: argparse.Namespace) -> None:
    with db.connect() as conn:
        try:
            parent = (
                lemon.own_id(conn, args.channel or "")
                if args.use_self
                else lemon.lemon_id(conn, args.lemon)
            )
        except (LookupError, ValueError, store.ChangedUnderneath) as error:
            _fail(args, str(error))

        listed = [
            child
            for child in children.of(conn, parent, _world())
            if children.shown(child, args.all)
        ]

    if args.json:
        result = {"lemon_id": parent, "children": [_as_json(c) for c in listed], "error": None}
        print(json.dumps(result, ensure_ascii=False))
        return

    now = time.time()
    for child in listed:
        print("\n".join(_lines(child, now, "")))


def add_parser(brief_subparsers: argparse._SubParsersAction) -> None:
    summary = "A parent's children, their places and sessions, and what holds up their cleanup"
    parser = brief_subparsers.add_parser(
        "children",
        help=summary,
        description=f"{summary}. A child whose Status is done is left out once its directory "
        "is known to be gone, unless --all. Whether a branch is merged is not checked.",
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument(
        "--self", dest="use_self", action="store_true", help="The lemon running this command"
    )
    target.add_argument(
        "lemon", nargs="?", help="The parent: a Lemon-ID, channel, or brief name (attached or not)"
    )
    parser.add_argument("--channel", help="This lemon's channel, overriding self detection")
    parser.add_argument("--all", action="store_true", help="Also list done children with no place")
    parser.add_argument("--json", action="store_true", help="Print the result as JSON")
    parser.set_defaults(func=cmd)
