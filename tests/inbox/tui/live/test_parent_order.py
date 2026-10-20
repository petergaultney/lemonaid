import dataclasses

import pytest

from lemonaid.groups.store import Group
from lemonaid.inbox import db, sections, view
from lemonaid.inbox.tui.live import inbox_entries, inbox_frame


def _frame(parent_group="A"):
    rows = [db.Notification(i, c, "", status="read") for i, c in enumerate(("a", "u", "b", "p"), 1)]
    return inbox_frame.Frame(
        active=view.Active(
            rows, {}, {}, frozenset(), {"a": ("A",), "u": ("A",), "b": ("A",), "p": (parent_group,)}
        ),
        pinned=frozenset(),
        focused_channels=frozenset(),
        shown=rows,
        folded=[],
        hidden=frozenset(),
        emojis={},
        groups=[Group(1, "A", 1.0, ()), Group(2, "B", 2.0, ())],
        wordybins={},
        other=[],
        numbers={},
        matching_ids=None,
        parents={"a": "p", "b": "p"},
    )


def _keys(frame, **kwargs):
    entries, _, _ = inbox_entries.entries(
        frame, frame.shown, frame.folded, (), False, frame.active.rows, **kwargs
    )
    return [e.key for e in entries]


@pytest.mark.parametrize("parent_group", ["A", "B"])
def test_layout_parent_two_children_and_unrelated_row(parent_group):
    frame = _frame(parent_group)
    assert _keys(frame) == (
        ["group:1", "4@1", "1@1", "2@1", "3@1"]
        if parent_group == "A"
        else ["group:1", "1@1", "2@1", "3@1", "group:2", "4@2"]
    )


def test_hidden_or_folded_parent_does_not_reorder_visible_rows():
    frame = _frame()
    parent = frame.shown.pop()
    assert _keys(frame) == ["group:1", "1@1", "2@1", "3@1"]
    frame.folded.append(parent)
    assert _keys(frame) == ["group:1", "1@1", "2@1", "3@1"]
    entries, _, _ = inbox_entries.entries(
        frame, frame.shown, frame.folded, (), True, frame.active.rows
    )
    assert [e.key for e in entries] == ["group:1", "4@1", "1@1", "2@1", "3@1"]


def test_explicit_arranger_order_takes_precedence():
    assert _keys(_frame(), parents_first=False) == ["group:1", "1@1", "2@1", "3@1", "4@1"]


@pytest.mark.parametrize("retained", ["pinned", "deaf"])
def test_pinned_and_deaf_child_keep_their_leading_position(retained):
    frame = _frame()
    entries, _ = sections.layout(
        frame.shown,
        [],
        {"a"} if retained == "pinned" else (),
        frame.active.memberships,
        frame.groups,
        {},
        deaf={"a"} if retained == "deaf" else (),
        parents=frame.parents,
    )
    assert [e.key for e in entries] == ["group:1", "1@1", "2@1", "4@1", "3@1"]


@pytest.mark.parametrize("matching", [{1, 2, 3, 4}, {1, 2, 3}])
def test_search_orders_only_matching_parents_and_children(matching):
    frame = dataclasses.replace(_frame(), matching_ids=matching)
    assert _keys(frame) == (
        ["group:1", "4@1", "1@1", "2@1", "3@1"]
        if 4 in matching
        else ["group:1", "1@1", "2@1", "3@1"]
    )
