"""A search keeps the group headers above the matching rows."""

from types import SimpleNamespace

import pytest

from lemonaid.groups.store import Group
from lemonaid.inbox import db
from lemonaid.inbox.tui.live import inbox_entries


def _n(i: int, channel: str) -> db.Notification:
    return db.Notification(i, channel, "", status="read")


def _frame(matching: set[int], collapsed: bool = False):
    return SimpleNamespace(
        matching_ids=matching,
        pinned=frozenset(),
        parents={},
        attached={},
        other=[],
        groups=[Group(1, "A", 1.0, (), collapsed), Group(2, "B", 2.0, (), False)],
        active=SimpleNamespace(
            memberships={"a1": ("A",), "a2": ("A",), "b1": ("B",)},
            cards={},
            rows=[],
            deaf=frozenset(),
        ),
    )


@pytest.mark.parametrize("ungrouped_first", [True, False])
def test_matches_sit_under_their_group_and_groups_without_matches_are_dropped(ungrouped_first):
    rows = [_n(1, "a1"), _n(2, "a2"), _n(3, "b1"), _n(4, "loose")]

    entries, _, _ = inbox_entries.entries(
        _frame({2, 4}), rows, [], frozenset(), False, ungrouped_first=ungrouped_first
    )

    assert [e.key for e in entries] == (
        ["4", "group:1", "2@1"] if ungrouped_first else ["group:1", "2@1", "4"]
    )


def test_a_collapsed_group_still_shows_its_matches():
    rows = [_n(1, "a1"), _n(3, "b1")]

    entries, _, _ = inbox_entries.entries(_frame({1}, collapsed=True), rows, [], frozenset(), False)

    assert [e.key for e in entries] == ["group:1", "1@1"]


def test_a_lemon_an_unread_reply_brought_back_leaves_the_fold():
    from lemonaid.inbox import db, sections

    lemon, quiet, reply = (
        db.Notification(1, "lemon", ""),
        db.Notification(2, "quiet", ""),
        db.Notification(3, "comments:lemon|/g.md", "", status="unread"),
    )
    entries = [sections.Row("1", lemon), sections.Row("3", reply)]

    left = inbox_entries.still_folded([lemon, quiet], entries, {"comments:lemon|/g.md": "lemon"})

    assert left == [quiet]


def test_a_search_keeps_the_lemon_of_a_matching_reply_in_the_other_pane():
    there, reply, quiet = (
        _n(5, "claude:there"),
        db.Notification(6, "comments:claude:there|/g.md", "", status="unread"),
        _n(7, "claude:quiet"),
    )
    frame = _frame({6})
    frame.other = [there, reply, quiet]
    frame.attached = {reply.channel: "claude:there"}

    _, _, other = inbox_entries.entries(frame, [], [], frozenset(), False)

    assert other == [there, reply]


def test_a_search_matching_only_a_read_reply_keeps_it_and_its_lemon():
    lemon, reply = _n(5, "lemon"), _n(6, "comments:lemon|/g.md")
    frame = _frame({6})
    frame.attached = {reply.channel: "lemon"}

    entries, _, _ = inbox_entries.entries(frame, [lemon, reply], [], frozenset(), False)

    assert [e.key for e in entries] == ["5", "6"]
