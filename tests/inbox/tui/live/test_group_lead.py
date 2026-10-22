import dataclasses

from lemonaid.groups.store import Group
from lemonaid.inbox import db, view
from lemonaid.inbox.tui.live import inbox_entries, inbox_frame


def _frame(parents, pinned=(), collapsed=False, extra_group=False, folded=()):
    rows = [db.Notification(i, c, "", status="read") for i, c in enumerate(("w1", "lead", "w2"), 1)]
    memberships = {c: ("A",) for c in ("w1", "lead", "w2")}
    groups = [Group(1, "A", 1.0, ("w1", "lead", "w2"), collapsed)]
    if extra_group:
        memberships["w1"] = ("A", "B")
        memberships["lead"] = ("A", "B")
        groups.append(Group(2, "B", 2.0, ("w1", "lead")))
    return inbox_frame.Frame(
        active=view.Active(rows, {}, {}, frozenset(), memberships),
        pinned=frozenset(pinned),
        focused_channels=frozenset(),
        shown=[n for n in rows if n.channel not in folded],
        folded=[n for n in rows if n.channel in folded],
        hidden=frozenset(),
        emojis={},
        groups=groups,
        wordybins={},
        other=[],
        numbers={},
        matching_ids=None,
        parents=parents,
    )


def _keys(frame, lead_first=True, **kwargs):
    entries, _, _ = inbox_entries.entries(
        frame,
        frame.shown,
        frame.folded,
        (),
        False,
        frame.active.rows,
        lead_first=lead_first,
        **kwargs,
    )
    return [e.key for e in entries]


_CHILDREN = {"w1": "lead", "w2": "lead"}


def _with_stranger(parents, **kwargs):
    frame = _frame(parents, **kwargs)
    stranger = db.Notification(4, "stranger", "", status="read")
    memberships = {**frame.active.memberships, "stranger": ("A",)}
    active = view.Active([*frame.active.rows, stranger], {}, {}, frozenset(), memberships)
    return dataclasses.replace(frame, active=active)


def test_lead_sorts_first_among_children():
    assert _keys(_frame(_CHILDREN)) == ["group:1", "2@1", "1@1", "3@1"]


def test_member_with_most_descendants_leads():
    frame = _frame({"w1": "lead", "w2": "w1"}, pinned={"w2"})
    assert _keys(frame) == ["group:1", "2@1", "3@1", "1@1"]


def test_a_stray_member_does_not_unseat_the_lead():
    frame = _with_stranger(_CHILDREN, pinned={"w1"})
    assert _keys(frame)[:3] == ["group:1", "2@1", "1@1"]


def test_no_lead_without_lineage():
    assert _keys(_frame({}, pinned={"w1"}))[:2] == ["group:1", "1@1"]


def test_collapsed_group_hides_the_lead_like_any_member():
    assert _keys(_frame(_CHILDREN, collapsed=True)) == ["group:1"]


def test_lead_sorts_above_a_pinned_member():
    assert _keys(_frame(_CHILDREN, pinned={"w2"})) == ["group:1", "2@1", "3@1", "1@1"]
    assert _keys(_frame(_CHILDREN, pinned={"w2", "lead"})) == ["group:1", "2@1", "3@1", "1@1"]


def test_pinned_member_of_a_collapsed_group_does_not_pull_its_lead():
    assert _keys(_frame(_CHILDREN, pinned={"w2"}, collapsed=True)) == ["group:1", "3@1"]


def test_a_drawn_child_pulls_a_folded_parent_into_view():
    frame = _frame(_CHILDREN, folded={"lead"})
    assert _keys(frame) == ["group:1", "2@1", "1@1", "3@1"]


def test_a_folded_parent_stays_folded_when_no_child_is_drawn():
    frame = _frame(_CHILDREN, folded={"lead", "w1", "w2"})
    assert _keys(frame) == []


def test_ancestors_are_not_pulled_without_the_option():
    frame = _frame(_CHILDREN, folded={"lead"})
    assert _keys(frame, lead_first=False) == ["group:1", "1@1", "3@1"]


def test_lead_of_one_group_only():
    keys = _keys(_frame(_CHILDREN, extra_group=True))
    assert keys[:4] == ["group:1", "2@1", "1@1", "3@1"]
    assert keys[4:] == ["group:2", "2@2", "1@2"]


def test_option_off_keeps_usual_order():
    frame = _frame(_CHILDREN, pinned={"w1"})
    assert _keys(frame, lead_first=False) == ["group:1", "1@1", "2@1", "3@1"]


def test_grandparent_leads_through_a_lemon_outside_the_group():
    frame = _frame({"w1": "outside", "outside": "lead", "w2": "w1"}, pinned={"w1"})
    assert _keys(frame)[:3] == ["group:1", "2@1", "1@1"]


def test_search_subset_keeps_the_group_lead():
    frame = dataclasses.replace(_frame(_CHILDREN, pinned={"w1"}), matching_ids={1, 2})
    assert _keys(frame) == ["group:1", "2@1", "1@1"]


def test_a_drawn_child_pulls_a_parent_the_inbox_hid_away():
    frame = _frame(_CHILDREN)
    shown = [n for n in frame.shown if n.channel != "lead"]
    assert _keys(dataclasses.replace(frame, shown=shown)) == ["group:1", "2@1", "1@1", "3@1"]
    assert _keys(dataclasses.replace(frame, shown=shown), lead_first=False) == [
        "group:1",
        "1@1",
        "3@1",
    ]
