from lemonaid.grove.draw import tag_fit
from lemonaid.grove.layout import stands

_TAG = tag_fit.Fitted(("abcdef",), 40, 10, (42, 9))


def test_a_list_hanging_from_the_tag_with_the_trunk_over_it_is_stood_on():
    assert stands.off(_TAG, (39, 10, 30, 3)) == ""
    assert stands.off(_TAG, (20, 10, 30, 3)) == ""


def test_a_list_below_the_trunk_says_how_far():
    assert "1 row below" in stands.off(_TAG, (39, 11, 30, 3))
    assert "3 rows below" in stands.off(_TAG, (39, 13, 30, 3))


def test_a_trunk_past_the_end_of_the_list_says_which_end():
    assert "2 columns past the list's right end" in stands.off(_TAG, (10, 10, 32, 3))
    assert "columns left of the list's left end" in stands.off(_TAG, (50, 10, 30, 3))


def test_a_list_beside_the_tree_is_called_beside():
    assert stands.off(_TAG, (60, 4, 30, 3)).startswith("the list is beside the tree")
