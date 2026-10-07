"""Direct links to a lemon's recorded tmux pane."""

import argparse
import os
import re
import sqlite3
import subprocess
import sys
from urllib.parse import quote, unquote, urlsplit

from .brief import lemon, store
from .inbox import db
from .tmux import navigation


def _target(value: str) -> str:
    if "://" in value:
        url = urlsplit(value)
        if url.scheme != "lemonaid" or url.netloc != "go" or url.query or url.fragment:
            raise ValueError("Expected lemonaid://go/<Lemon-ID-or-channel>")

        value = unquote(url.path.removeprefix("/"))
    if not value or re.search(r"[\s/\x00-\x1f\x7f]", value):
        raise ValueError("Expected a Lemon-ID or channel")

    return value


def _notification(conn: sqlite3.Connection, target: str) -> db.Notification:
    found = db.get_by_channel(conn, target, unread_only=False)
    if found is None:
        found = lemon.attachment(conn, target).notification
    if found is None or found.status == "archived":
        raise LookupError(f"No active lemon for {target!r}")

    return found


def _tmux(command: list[str], *args: str) -> str:
    result = subprocess.run(
        [*command, *args], capture_output=True, text=True, check=True, timeout=5
    )
    return result.stdout.strip()


def _pane(command: list[str], found: db.Notification) -> str:
    metadata = found.metadata
    tty = metadata.get("tty")
    recorded_pane = metadata.get("tmux_pane_identity")
    order = metadata.get("tmux_session_order")
    if not tty or not recorded_pane or not order:
        raise LookupError(
            "This lemon has no recorded tmux pane identity; wait for its next notification"
        )

    panes = _tmux(
        command,
        "list-panes",
        "-a",
        "-F",
        "#{pane_id}|#{pane_tty}|#{session_name}|#{session_created}|#{start_time}|#{session_id}",
    )
    matches: set[str] = set()
    for line in panes.splitlines():
        parts = line.split("|")
        if len(parts) != 6 or parts[1] != tty:
            continue
        pane, _, session, created, started, session_id = parts
        if [pane, int(started)] != recorded_pane:
            continue
        if metadata.get("tmux_session") and session != metadata["tmux_session"]:
            continue
        if [int(created), int(started), int(session_id.lstrip("$"))] != list(order):
            continue
        if float(created) > found.created_at:
            continue
        matches.add(pane)
    if len(matches) != 1:
        raise LookupError("The lemon's recorded tmux pane is gone or ambiguous; no jump made")

    return matches.pop()


def _client(command: list[str], explicit: str, source_pane: str) -> str:
    clients = _tmux(command, "list-clients", "-F", "#{client_name}|#{session_name}")
    rows = [line.split("|", 1) for line in clients.splitlines() if "|" in line]
    if explicit:
        if explicit not in [row[0] for row in rows]:
            raise LookupError(f"No attached tmux client {explicit!r}")

        return explicit

    if source_pane:
        panes = _tmux(command, "list-panes", "-a", "-F", "#{pane_id}|#{session_name}")
        sessions = {
            parts[1]
            for line in panes.splitlines()
            if len(parts := line.split("|", 1)) == 2 and parts[0] == source_pane
        }
        rows = [row for row in rows if row[1] in sessions]
    if len(rows) != 1:
        choices = ", ".join(row[0] for row in rows) or "none"
        raise LookupError(f"Expected one attached tmux client; found {choices}. Use --client NAME")

    return rows[0][0]


def _cmd_go(args: argparse.Namespace) -> None:
    try:
        target = _target(args.target)
        if args.link:
            url = f"lemonaid://go/{quote(target, safe='')}"
            print(f"\x1b]8;;{url}\x1b\\{target}\x1b]8;;\x1b\\")
            return

        with db.connect() as conn:
            found = _notification(conn, target)
        if found.switch_source != "tmux":
            raise ValueError("lemonaid go currently supports tmux lemons only")

        socket = found.metadata.get("tmux_socket")
        command = navigation.server_args(socket)
        own_socket = os.environ.get("TMUX", "").split(",", 1)[0]
        source_pane = os.environ.get("TMUX_PANE", "") if not socket or socket == own_socket else ""
        pane = _pane(command, found)
        client = _client(command, args.client, source_pane)
        _tmux(command, "switch-client", "-c", client, "-t", pane)
    except (
        LookupError,
        ValueError,
        OSError,
        subprocess.SubprocessError,
        store.ChangedUnderneath,
    ) as error:
        print(f"lemonaid go: {error}", file=sys.stderr)
        raise SystemExit(1) from error


def setup_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("go", help="Jump to a lemon by Lemon-ID, channel, or link")
    parser.add_argument("target", help="Lemon-ID, channel, or lemonaid://go/... URL")
    parser.add_argument(
        "--client", default="", help="Exact attached tmux client name (usually /dev/ttysNNN)"
    )
    parser.add_argument(
        "--link", action="store_true", help="Print an OSC 8 link instead of jumping"
    )
    parser.set_defaults(func=_cmd_go)
