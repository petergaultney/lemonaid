import pytest

from lemonaid.inbox import db, parent_order


@pytest.mark.parametrize(
    ("names", "parents", "expected"),
    [
        ("aubp", {"a": "p", "b": "p"}, "paub"),
        ("aub", {"a": "missing"}, "aub"),
        ("gaubp", {"g": "b", "a": "p", "b": "p"}, "pabgu"),
        ("abc", {"a": "b", "b": "a", "c": "c"}, "bac"),
    ],
)
def test_visible_ancestors_precede_children_with_stable_siblings(names, parents, expected):
    rows = [db.Notification(i, name, "") for i, name in enumerate(names)]
    assert "".join(n.channel for n in parent_order.ordered(rows, parents)) == expected


def test_long_ancestry_does_not_use_the_python_call_stack():
    rows = [db.Notification(i, str(i), "") for i in range(1500)]
    parents = {str(i): str(i + 1) for i in range(1499)}
    assert parent_order.ordered(rows, parents) == rows[::-1]
