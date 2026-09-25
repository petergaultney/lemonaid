"""Brief listing and stable-ID CLI queries."""

import argparse
import json
import sys

from ..inbox import db
from . import attached, identity, selector, store


def _fail(args: argparse.Namespace, error: str) -> None:
    if args.json:
        print(json.dumps({"error": error}))
    else:
        print(error, file=sys.stderr)

    raise SystemExit(1)


def cmd_list(args: argparse.Namespace) -> None:
    with db.connect() as conn:
        attached.claim_pending(conn)
        entries = [
            {
                "path": str(a.path),
                "channel": a.channel or None,
                "pending": not a.channel,
                "id": a.notification.id if a.notification else None,
                "name": a.notification.name if a.notification else None,
                "archived": a.notification.is_archived if a.notification else None,
                "tmux_session": a.tmux_session or None,
                "tmux_window": a.tmux_window or None,
            }
            for a in attached.everything(conn)
        ]

    if args.json:
        print(json.dumps(entries, ensure_ascii=False))
        return

    for entry in entries:
        who = entry["channel"] or f"(next lemon in {entry['tmux_session']}:{entry['tmux_window']})"
        print(f"{entry['path']}  {who}")


def cmd_id(args: argparse.Namespace) -> None:
    with db.connect() as conn:
        chosen, error = selector.select(conn, args)
        if chosen is None or not chosen.channel:
            _fail(args, error or "No lemon at that target")

        attached.claim_pending(conn)
        path = attached.by_channel(conn, [chosen.channel]).get(chosen.channel)
        if path is None:
            _fail(args, f"No brief attached to {chosen.channel!r}")

        try:
            lemon_id = identity.ensure(conn, path)
        except (ValueError, store.ChangedUnderneath) as cause:
            _fail(args, str(cause))

    if args.json:
        print(
            json.dumps(
                {"lemon_id": lemon_id, "channel": chosen.channel, "path": str(path), "error": None}
            )
        )
    else:
        print(lemon_id)
