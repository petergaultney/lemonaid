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
