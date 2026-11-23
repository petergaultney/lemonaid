from lemonaid.grove.layout import labels, letters
from lemonaid.grove.model import Tree


def _tree(key: str, lead: bool = False) -> Tree:
    return Tree(key, key, (), lead)


def _short(*keys: str) -> dict[str, str]:
    return {key: key for key in keys}


def test_a_tree_with_an_empty_letter_gets_one():
    spots = {"a": {"letter": ""}, "b": {"letter": "b"}}
    letters.settle([_tree("a"), _tree("b")], spots, _short("a", "b"))
    assert spots["a"]["letter"] == "a"
    assert spots["b"]["letter"] == "b"


def test_the_leads_spot_holds_no_letter_so_others_may_take_it():
    spots = {"boss": {"letter": "h"}, "hat": {"letter": ""}}
    letters.settle([_tree("boss", lead=True), _tree("hat")], spots, _short("boss", "hat"))
    assert spots["boss"]["letter"] == ""
    assert spots["hat"]["letter"] == "h"


def test_a_gone_trees_letter_goes_to_a_live_tree_without_one():
    spots = {"live": {"letter": ""}, "gone": {"letter": "i", "gone_since": 1.0}}
    letters.settle([_tree("live")], spots, _short("live"))
    assert spots["live"]["letter"] == "i"
    assert spots["gone"]["letter"] == ""


def test_a_tree_past_the_supply_stays_keyless_until_a_letter_frees():
    keys = [f"t{i}" for i in range(len(labels.LETTERS))]
    spots = {key: {"letter": ""} for key in keys}
    letters.settle([_tree(key) for key in keys], spots, _short(*keys))
    assert [spots[key]["letter"] for key in keys].count("") == 1


def test_a_lead_after_a_keyless_tree_still_frees_its_letter_in_one_pass():
    trees = [_tree("hat"), _tree("boss", lead=True)]
    spots = {"hat": {"letter": ""}, "boss": {"letter": "h"}}
    letters.settle(trees, spots, _short("hat", "boss"))
    assert spots["hat"]["letter"] == "h"
