from lemonaid.groups.store import Group
from lemonaid.inbox import db, sections


def _n(i: int, channel: str, unread: bool = False) -> db.Notification:
    return db.Notification(i, channel, "", status="unread" if unread else "read")


def _group(i: int, name: str, collapsed: bool = False) -> Group:
    return Group(i, name, float(i), (), collapsed)


def _keys(entries) -> list[str]:
    return [e.key for e in entries]


def test_ungrouped_pins_then_each_group_under_its_header_then_the_rest():
    pin, loose, a1, b1 = _n(1, "pin"), _n(2, "loose"), _n(3, "a1"), _n(4, "b1")

    entries, folded = sections.layout(
        [pin, a1, loose, b1],
        [],
        {"pin"},
        {"a1": ("A",), "b1": ("B",)},
        [_group(1, "A"), _group(2, "B")],
        {},
    )

    assert _keys(entries) == ["1", "group:1", "3@1", "group:2", "4@2", "2"]
    assert folded == []


def test_a_pinned_lemon_heads_its_group_and_stays_when_the_group_collapses():
    lead, worker = _n(1, "lead"), _n(2, "worker")
    members = {"lead": ("A",), "worker": ("A",)}

    open_, _ = sections.layout([lead, worker], [], {"lead"}, members, [_group(1, "A")], {})
    shut, _ = sections.layout(
        [lead, worker], [], {"lead"}, members, [_group(1, "A", collapsed=True)], {}
    )

    assert _keys(open_) == ["group:1", "1@1", "2@1"]
    assert _keys(shut) == ["group:1", "1@1"]
    assert shut[0].count == 2


def test_a_lemon_in_two_groups_is_drawn_in_both():
    both = _n(5, "both")

    entries, _ = sections.layout(
        [both], [], set(), {"both": ("A", "B")}, [_group(1, "A"), _group(2, "B")], {}
    )

    assert _keys(entries) == ["group:1", "5@1", "group:2", "5@2"]
    assert {sections.notification_id(k) for k in _keys(entries)} == {None, 5}


def test_a_collapsed_group_keeps_its_header_and_its_most_pressing_band():
    calm, urgent = _n(1, "calm"), _n(2, "urgent", unread=True)

    entries, _ = sections.layout(
        [calm, urgent],
        [],
        set(),
        {"calm": ("A",), "urgent": ("A",)},
        [_group(1, "A", collapsed=True)],
        {"calm": "waiting", "urgent": "blocked"},
    )

    [header] = entries
    assert isinstance(header, sections.Header)
    assert (header.count, header.band) == (2, "blocked")


def test_a_group_with_no_rows_is_not_drawn():
    entries, _ = sections.layout([_n(1, "a")], [], set(), {}, [_group(1, "Empty")], {})

    assert _keys(entries) == ["1"]


def test_a_folded_row_in_a_group_hides_in_place_and_the_rest_stay_in_the_fold():
    awake, quiet_grouped, quiet_loose = _n(3, "a"), _n(1, "g"), _n(2, "l")
    args = ([awake], [quiet_grouped, quiet_loose], set(), {"a": ("A",), "g": ("A",)})

    closed, folded = sections.layout(*args, [_group(1, "A")], {})
    opened, _ = sections.layout(*args, [_group(1, "A")], {}, fold_open=True)

    assert _keys(closed) == ["group:1", "3@1"]
    assert closed[0].tally == "1/2"
    assert folded == [quiet_loose]
    assert _keys(opened) == ["group:1", "3@1", "1@1"]


def test_without_groups_the_order_is_unchanged():
    rows = [_n(1, "pin"), _n(2, "a"), _n(3, "b")]

    entries, _ = sections.layout(rows, [], {"pin"}, {}, [], {})

    assert _keys(entries) == ["1", "2", "3"]


def test_header_keys_name_their_group_and_no_notification():
    assert sections.group_id("group:7") == 7
    assert sections.notification_id("group:7") is None
    assert sections.notification_id("12@7") == 12
    assert sections.group_id("12@7") is None


def test_a_group_floats_to_the_top_of_its_most_pressing_rows_band():
    alarm, blocked, chatty, quiet = (
        _n(1, "alarm"),
        _n(2, "blocked"),
        _n(3, "chatty", unread=True),
        _n(4, "quiet"),
    )
    member, idle = _n(5, "member"), _n(6, "idle")
    statuses = {"alarm": "alert", "blocked": "blocked", "member": "blocked"}

    entries, _ = sections.layout(
        [alarm, blocked, member, chatty, quiet, idle],
        [],
        set(),
        {"member": ("Busy",), "idle": ("Calm",)},
        [_group(1, "Calm"), _group(2, "Busy")],
        statuses,
    )

    assert _keys(entries) == ["1", "group:2", "5@2", "2", "3", "group:1", "6@1", "4"]


def test_a_group_with_every_row_folded_is_drawn_only_with_the_fold_open():
    loose, quiet = _n(1, "l"), _n(2, "q")
    args = ([loose], [quiet], set(), {"q": ("A",)}, [_group(1, "A")], {})

    assert _keys(sections.layout(*args)[0]) == ["1"]
    assert _keys(sections.layout(*args, fold_open=True)[0]) == ["group:1", "2@1", "1"]
