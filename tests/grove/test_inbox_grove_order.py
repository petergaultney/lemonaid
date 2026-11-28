from lemonaid.grove.source import inbox_keys
from lemonaid.grove.tui.frame import Grove
from lemonaid.inbox import db, sections

from .keys.test_step import ARRANGEMENT, BIG, BLOCKS, LEAD, PAIR


def _rows(*channels: str) -> list[sections.Row]:
    return [sections.Row(str(i), db.Notification(i, c, "")) for i, c in enumerate(channels)]


def test_a_zoomed_blocks_rows_group_by_tree_with_the_lead_tree_first():
    grove = Grove(BLOCKS, ARRANGEMENT, {})
    by_tree = {t.key: [lemon.channel for lemon in t.lemons] for t in (LEAD, BIG, PAIR)}
    shuffled = [
        by_tree[PAIR.key][1],
        by_tree[BIG.key][2],
        by_tree[LEAD.key][0],
        by_tree[BIG.key][0],
        by_tree[PAIR.key][0],
        by_tree[BIG.key][1],
    ]

    ordered = inbox_keys.in_grove_order(_rows(*shuffled), grove, "1")

    letters = {k: ARRANGEMENT.trees[("shop-postgres", k)].letter for k in by_tree}
    later = sorted((BIG.key, PAIR.key), key=letters.get)
    assert [r.notification.channel for r in ordered] == [
        *by_tree[LEAD.key],
        *by_tree[later[0]],
        *by_tree[later[1]],
    ]


def test_a_reply_row_stays_right_after_its_lemon_when_a_block_is_zoomed():
    grove = Grove(BLOCKS, ARRANGEMENT, {})
    lead = [lemon.channel for lemon in LEAD.lemons]
    big = [lemon.channel for lemon in BIG.lemons]
    reply = "item:" + lead[0] + "|/g.md"

    ordered = inbox_keys.in_grove_order(
        _rows(big[0], lead[0], reply, *lead[1:]), grove, "1", {reply: lead[0]}
    )

    channels = [r.notification.channel for r in ordered]
    assert channels.index(reply) == channels.index(lead[0]) + 1


def test_zooming_into_a_block_keeps_its_lemons_reply_rows():
    from lemonaid.groups.store import Group
    from lemonaid.inbox import view
    from lemonaid.inbox.tui.live import inbox_frame

    grove = Grove(BLOCKS, ARRANGEMENT, {})
    lemon = LEAD.lemons[0].channel
    reply = f"item:{lemon}|/g.md"
    rows = [db.Notification(1, lemon, ""), db.Notification(2, reply, "", status="unread")]
    frame = inbox_frame.Frame(
        active=view.Active(rows, {}, {}, frozenset(), {}),
        pinned=frozenset(),
        focused_channels=frozenset(),
        shown=rows,
        folded=[],
        hidden=frozenset(),
        emojis={},
        groups=[Group(1, "shop-postgres", 1.0, ())],
        wordybins={},
        other=[],
        numbers={},
        matching_ids=None,
        attached={reply: lemon},
    )

    zoomed = inbox_keys.only_block(frame, grove, "1")

    assert zoomed.matching_ids == {1, 2}
