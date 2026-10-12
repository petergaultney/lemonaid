"""A lemon marked deaf is never hidden by a fold, filter or collapsed group."""

import pytest

from lemonaid.groups.store import Group
from lemonaid.inbox import db, order, sections, view
from lemonaid.inbox.arrange import answer
from lemonaid.inbox.tui.brief_cards import CardBrief


def _n(i: int, channel: str, unread: bool = False) -> db.Notification:
    return db.Notification(i, channel, "", status="unread" if unread else "read")


def _card(status: str = "", mark: str = "") -> CardBrief:
    return CardBrief(status, "", 0.0, mark=mark)


@pytest.mark.parametrize("status", ["", "idle", "waiting", "working", "review", "blocked"])
@pytest.mark.parametrize("read", [True, False])
def test_a_deaf_row_never_folds_whatever_statuses_are_folded(status, read):
    deaf = _n(1, "deaf", unread=not read)
    statuses = {"deaf": status or "deaf"}

    shown, folded = order.fold(
        [deaf],
        statuses,
        set(),
        {status, "deaf", "idle", "review", "blocked"},
        set(),
        {"deaf"},
    )

    assert (shown, folded) == ([deaf], [])


def test_a_row_that_is_not_deaf_still_folds():
    quiet = _n(1, "quiet")

    shown, folded = order.fold([quiet], {"quiet": "idle"}, set(), {"idle"}, set(), set())

    assert (shown, folded) == ([], [quiet])


def _active(rows, cards) -> view.Active:
    return view.Active(rows, cards, {}, frozenset(cards))


def test_a_deaf_reviewer_stays_in_the_inbox_and_a_quiet_one_does_not():
    deaf, quiet = _n(1, "deaf"), _n(2, "quiet")
    active = _active([deaf, quiet], {"deaf": _card(mark="deaf"), "quiet": _card()})

    assert view.inbox_rows(active, set(), set()) == [deaf]


def test_a_deaf_row_in_a_collapsed_group_is_still_drawn():
    deaf, quiet = _n(1, "deaf"), _n(2, "quiet")
    members = {"deaf": ("A",), "quiet": ("A",)}
    group = Group(1, "A", 1.0, (), True)

    entries, _ = sections.layout([deaf, quiet], [], set(), members, [group], {}, deaf={"deaf"})

    assert [e.key for e in entries] == ["group:1", "1@1"]


def test_a_deaf_row_in_a_group_is_drawn_while_the_fold_is_closed():
    deaf = _n(1, "deaf")
    group = Group(1, "A", 1.0, (), False)

    entries, _ = sections.layout([], [deaf], set(), {"deaf": ("A",)}, [group], {}, deaf={"deaf"})

    assert [e.key for e in entries] == ["group:1", "1@1"]


def test_an_arranger_cannot_fold_a_deaf_row():
    shown = [_n(1, "a"), _n(2, "deaf")]

    arranged = answer.apply({"rows": [1], "folded": [2]}, shown, [], False, {"deaf"})

    assert [n.id for n in arranged.shown] == [1, 2]
    assert arranged.folded == []


def test_only_a_card_marked_deaf_is_in_active_deaf():
    rows = [_n(1, "deaf"), _n(2, "dead"), _n(3, "plain")]
    cards = {"deaf": _card(mark="deaf"), "dead": _card(mark="dead"), "plain": _card()}

    assert _active(rows, cards).deaf == {"deaf"}
