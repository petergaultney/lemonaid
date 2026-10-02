"""An arranger's answer decides the order and the fold, and never loses a row."""

import pytest

from lemonaid.inbox import db
from lemonaid.inbox.arrange import answer


def _row(i: int, unread: bool = False) -> db.Notification:
    return db.Notification(i, f"claude:{i}", "m", status="unread" if unread else "read")


def _ids(rows: list[db.Notification]) -> list[int]:
    return [n.id for n in rows]


def test_the_answer_orders_and_folds_rows():
    shown, folded = [_row(1), _row(2), _row(3)], [_row(4)]

    arranged = answer.apply(
        {"rows": [3, 1], "folded": [2, 4], "fold_label": "quiet"}, shown, folded, False
    )

    assert (_ids(arranged.shown), _ids(arranged.folded)) == ([3, 1], [2, 4])
    assert arranged.fold_label == "quiet"
    assert arranged.problems == []


def test_rows_left_out_go_where_the_inbox_puts_them():
    arranged = answer.apply({"rows": [3]}, [_row(1), _row(2), _row(3)], [_row(4)], False)

    assert (_ids(arranged.shown), _ids(arranged.folded)) == ([3, 1, 2], [4])
    assert arranged.problems == [
        "rows 1, 2 left out, added where the inbox's own order puts them",
        "rows 4 left out, added where the inbox's own order puts them",
    ]


def test_an_unread_row_stays_out_of_the_fold():
    arranged = answer.apply({"rows": [1], "folded": [2]}, [_row(1), _row(2, True)], [], False)

    assert (_ids(arranged.shown), _ids(arranged.folded)) == ([1, 2], [])
    assert arranged.problems == ["folded: row 2 is unread, kept in the list"]


def test_the_user_can_let_unread_rows_fold():
    arranged = answer.apply({"rows": [1], "folded": [2]}, [_row(1), _row(2, True)], [], True)

    assert _ids(arranged.folded) == [2]


def test_unknown_and_repeated_ids_and_fields_are_ignored():
    arranged = answer.apply({"rows": [2, 99, 2, 1], "colour": "red"}, [_row(1), _row(2)], [], False)

    assert _ids(arranged.shown) == [2, 1]
    assert arranged.problems == [
        "unknown field 'colour' ignored",
        "rows: no row 99, ignored",
        "rows: row 2 placed twice, first kept",
    ]


@pytest.mark.parametrize(
    ("reply", "error"),
    [
        ([1, 2], "must be a JSON object, not list"),
        ({"rows": ["1"]}, "'rows' must be a list of row ids"),
        ({"rows": [True]}, "'rows' must be a list of row ids"),
        ({"fold_label": 3}, "'fold_label' must be a string"),
        ({"error": "KeyError: 'brief'"}, "arranger says: KeyError: 'brief'"),
    ],
)
def test_an_unusable_answer_is_an_error(reply, error):
    with pytest.raises(answer.AnswerError, match=error):
        answer.apply(reply, [_row(1)], [], False)


def test_the_default_answer_is_the_inbox_order():
    snapshot = {
        "rows": [
            {"id": 7, "default": {"position": 1, "folded": False}},
            {"id": 5, "default": {"position": 0, "folded": False}},
            {"id": 9, "default": {"position": 2, "folded": True}},
        ]
    }

    assert answer.default(snapshot) == {"rows": [5, 7], "folded": [9]}
