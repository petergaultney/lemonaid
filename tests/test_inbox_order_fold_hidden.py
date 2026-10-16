from lemonaid.inbox import db, order


def _n(i: int, channel: str, status: str = "read") -> db.Notification:
    return db.Notification(i, channel, "", status=status)


def test_hidden_lemons_fold_even_when_unread_but_not_pinned_or_deaf():
    rows = [_n(1, "a", "unread"), _n(2, "b"), _n(3, "c"), _n(4, "d")]

    shown, folded = order.fold(rows, {}, {"b"}, (), set(), {"c"}, {"a", "b", "c"})

    assert [n.channel for n in folded] == ["a"]
    assert [n.channel for n in shown] == ["b", "c", "d"]
