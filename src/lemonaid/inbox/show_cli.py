"""`lemonaid inbox show`: the inbox as `lma` draws it, for a lemon that can't see the screen."""

__lazy_modules__ = [
    "lemonaid.brief",
    "lemonaid.inbox.tui.live",
    "lemonaid.inbox.tui.rows",
]

import argparse
import json
import time
from collections import abc
from typing import Any

from .. import brief
from . import db, headless_view, sections, turns
from .tui.live import inbox_entries, inbox_frame
from .tui.rows import brief_cards

_MESSAGE = 100  # characters of a last message shown without --verbose


def _state(n: db.Notification, card: brief_cards.CardBrief | None, now: float) -> str:
    if card is not None:
        return card.age(now)

    return "blocked" if n.asks else "active" if turns.mid_turn(n, now) else "idle"


def _row(
    n: db.Notification,
    frame: inbox_frame.Frame,
    lemon_ids: abc.Mapping[str, str],
    group: str,
    folded: bool,
    now: float,
) -> dict[str, Any]:
    card = frame.active.cards.get(n.channel)
    path = frame.active.briefs.get(n.channel)
    return {
        "id": n.id,
        "channel": n.channel,
        "lemon": lemon_ids.get(n.channel, ""),
        "name": n.name or "",
        "emoji": frame.emojis.get(n.channel, ""),
        "group": group,
        "folded": folded,
        "unread": n.is_unread,
        "pinned": n.channel in frame.pinned,
        "state": _state(n, card, now),
        "needs": card.needs_line if card else "",
        "waiting_on": card.waiting_line if card else "",
        "running": card.running_line if card else "",
        "stuck": card.stuck_line if card else "",
        "message": n.message,
        "brief": str(path) if path else "",
    }


def _shown(
    frame: inbox_frame.Frame,
    entries: abc.Iterable[inbox_entries.Entry],
    folded: abc.Iterable[db.Notification],
    lemon_ids: abc.Mapping[str, str],
    now: float,
) -> abc.Iterator[dict[str, Any]]:
    group = ""
    for e in entries:
        if isinstance(e, sections.Header):
            group = e.group.name
            yield {"group": group, "shown": e.visible, "members": len(e.group.members)}
        else:
            in_group = sections.row_group_id(e.key) is not None
            yield _row(e.notification, frame, lemon_ids, group if in_group else "", False, now)
    for n in folded:
        yield _row(
            n, frame, lemon_ids, ", ".join(frame.active.memberships.get(n.channel, ())), True, now
        )


def _row_lines(row: abc.Mapping[str, Any], indent: str, verbose: bool) -> abc.Iterator[str]:
    name = " ".join(part for part in (row["emoji"], row["name"] or row["channel"]) if part)
    flags = "".join(f" [{flag}]" for flag in (row["lemon"], "pinned" * row["pinned"]) if flag)
    yield f"{indent}{row['id']:>6} {'●' if row['unread'] else ' '} {row['state']:<14} {name}{flags}"
    message = " ".join(row["message"].split())
    for line in (
        row["needs"],
        row["waiting_on"] and f"Waiting on: {row['waiting_on']}",
        row["running"] and f"Running: {row['running']}",
        row["stuck"],
        message if verbose or len(message) <= _MESSAGE else message[: _MESSAGE - 3] + "...",
    ):
        if line:
            yield f"{indent}{'':>23} {line}"


def _text(
    items: abc.Sequence[abc.Mapping[str, Any]], fold_label: str, folded: bool, verbose: bool
) -> abc.Iterator[str]:
    for item in items:
        if "id" not in item:
            yield f"{item['group']} ({item['shown']}/{item['members']}):"
        elif not item["folded"]:
            yield from _row_lines(item, "  " if item["group"] else "", verbose)
    rows = [item for item in items if item.get("folded")]
    if rows and folded:
        yield f"{fold_label or 'folded'} ({len(rows)}):"
        for row in rows:
            yield from _row_lines(row, "  ", verbose)
    elif rows:
        yield f"{len(rows)} folded{f' as {fold_label!r}' * bool(fold_label)}; --folded lists them"


def cmd_show(args: argparse.Namespace) -> None:
    now = time.time()
    with db.connect() as conn:
        frame, entries, folded, fold_label, error = headless_view.drawn(conn, args.stuck, now)
        lemon_ids = brief.identity.by_channel(conn)
    items = list(_shown(frame, entries, folded, lemon_ids, now))
    if args.json:
        print(
            json.dumps(
                {
                    "groups": [item for item in items if "id" not in item],
                    "rows": [item for item in items if "id" in item],
                    "fold_label": fold_label,
                    "arrange_error": error,
                }
            )
        )
        return

    if error:
        print(f"arrange: {error}; in lemonaid's own order")
    for line in _text(items, fold_label, args.folded, args.verbose):
        print(line)


def add_parser(inbox_subparsers: argparse._SubParsersAction) -> None:
    parser = inbox_subparsers.add_parser(
        "show",
        help="Print the inbox as lma draws it: order, groups, status and the fold",
        description="Every session lma lists, in its order and under its groups, with the "
        "status and the Needs and Waiting on lines its card shows. Runs the configured "
        "arranger and attention mode as lma does.",
    )
    parser.add_argument("--folded", action="store_true", help="List the folded rows too")
    parser.add_argument(
        "--stuck",
        action="store_true",
        help="Fetch the PRs lemons wait on from GitHub, for lma's stuck lines",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Full last messages")
    parser.add_argument("--json", action="store_true", help="Every row, folded too, as JSON")
    parser.set_defaults(func=cmd_show)
