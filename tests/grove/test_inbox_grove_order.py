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

    letters = {k: ARRANGEMENT.trees[("oria-postgres", k)].letter for k in by_tree}
    later = sorted((BIG.key, PAIR.key), key=letters.get)
    assert [r.notification.channel for r in ordered] == [
        *by_tree[LEAD.key],
        *by_tree[later[0]],
        *by_tree[later[1]],
    ]
