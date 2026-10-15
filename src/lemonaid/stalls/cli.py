"""`lemonaid lemon doctor --stalls`: the stuck lines the inbox cards show, as text."""

__lazy_modules__ = ["lemonaid.inbox", "lemonaid.inbox.tui.rows"]

import json
import time

from ..config import load_config
from ..inbox import db, presence, view
from ..inbox.tui.rows import brief_cards
from . import inbox, pulls, report


def run(as_json: bool) -> int:
    """Print every stall; the exit code is 1 when there is any."""
    config = load_config()
    now = time.time()
    with db.connect() as conn:
        active = view.ordered_active(
            conn, None, brief_cards.BriefCache(), presence.Probe(), False, now
        )
        found = pulls.find(inbox.lemons(conn, active), config.brief.vaults)

    snapshots = {key: inbox.fetch(key) for key in dict.fromkeys(pull.key for pull in found)}
    stalls = report.find(found, snapshots, now, config.inbox.stall_minutes)
    names = {n.channel: n.name or n.channel for n in active.rows}
    if as_json:
        print(
            json.dumps(
                [{"lemon": names.get(s.channel, s.channel), "stuck": s.line} for s in stalls]
            )
        )
    else:
        print(f"{len(stalls)} stalled")
        for stall in stalls:
            print(f"  {names.get(stall.channel, stall.channel)}  {stall.line}")
    return 1 if stalls else 0
