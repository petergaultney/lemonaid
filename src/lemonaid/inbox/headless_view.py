"""The inbox `lma` would draw now, built without a screen: no focus, search or cursor."""

__lazy_modules__ = [
    "lemonaid.inbox.tui.live",
    "lemonaid.inbox.tui.rows",
    "lemonaid.stalls",
]

import concurrent.futures
import sqlite3
import time

from ..config import Config, load_config
from ..stalls import inbox as stalls_inbox
from . import attention, db, presence, sections
from .tui.live import inbox_arrange, inbox_entries, inbox_frame
from .tui.rows import brief_cards, pr_numbers

_ARRANGE_WAIT = 5.0  # an arranger's first answer includes its start-up


def _frame(
    conn: sqlite3.Connection, config: Config, stalls: stalls_inbox.Tracker, now: float
) -> inbox_frame.Frame:
    return inbox_frame.load(
        conn,
        config,
        brief_cards.BriefCache(),
        presence.Probe(),
        pr_numbers.Cache(),
        stalls,
        env_filter=None,
        focused=frozenset(),
        search_text=None,
        current_key=None,
        other_key=None,
        unfolded_ids=frozenset(),
        shared_names=frozenset(),
        now=now,
        attention_mode=attention.load(),
    )


def _with_stalls(
    conn: sqlite3.Connection, config: Config, stalls: stalls_inbox.Tracker, now: float
) -> inbox_frame.Frame:
    """The frame again once the PRs its lemons wait on are fetched, as `lma`'s worker does."""
    keys = stalls.due(time.monotonic())
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for key, snap in zip(keys, pool.map(stalls_inbox.fetch, keys), strict=False):
            stalls.store(key, snap, time.monotonic())
    return _frame(conn, config, stalls, now)


def _arranged(
    config: Config, frame: inbox_frame.Frame
) -> tuple[list[db.Notification], list[db.Notification], str, list[db.Notification], bool, str]:
    """The arranger's shown and folded rows, fold label and group order, whether its answer
    was applied, and why not.

    A second ask reports a failure the first one waited out: an exit, or the arranger's
    own no-answer timeout.
    """
    arrangement = inbox_arrange.Arrangement(config, budget=_ARRANGE_WAIT)
    try:
        for _ in range(2):
            shown, folded, fold_label, group_order = arrangement.arranged(
                frame.active,
                frame.shown,
                frame.folded,
                frame.pinned,
                frame.hidden,
                frame.emojis,
                True,
                40,
            )
            applied = not arrangement.parents_first  # cleared only when an answer is applied
            if applied or arrangement.error or not config.inbox.arrange:
                break
    finally:
        arrangement.close()
    error = arrangement.error or (
        f"no answer in {_ARRANGE_WAIT:g}s" if config.inbox.arrange and not applied else ""
    )
    return shown, folded, fold_label, group_order, applied, error


def drawn(
    conn: sqlite3.Connection, stuck: bool, now: float
) -> tuple[inbox_frame.Frame, list[inbox_entries.Entry], list[db.Notification], str, str]:
    """The frame, its entries in drawing order, every row not drawn, the fold's label, and
    why the arranger's answer went unused.
    """
    config = load_config()
    stalls = stalls_inbox.Tracker()
    frame = _frame(conn, config, stalls, now)
    if stuck:
        frame = _with_stalls(conn, config, stalls, now)
    shown, folded, fold_label, group_order, applied, error = _arranged(config, frame)
    entries, _folded, _other = inbox_entries.entries(
        frame,
        shown,
        folded,
        frozenset(),
        False,
        group_order,
        ungrouped_first=config.inbox.ungrouped_first,
        parents_first=not applied,
        lead_first=config.tui.group_lead_first,
    )
    drawn = {e.notification.id for e in entries if isinstance(e, sections.Row)}
    return (
        frame,
        entries,
        [
            n for n in [*shown, *folded] if n.id not in drawn
        ],  # a group's folded members hide in place
        fold_label,
        error,
    )
