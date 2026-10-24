from lemonaid.grove.tui.keys import Where, step, uses

from .test_step import ARRANGEMENT, BLOCKS, letter


def _uses(key: str, where: Where | None = None) -> bool:
    return uses(where or Where(), key, BLOCKS, ARRANGEMENT)


def test_digits_escape_and_search_belong_to_the_grove():
    assert all(_uses(key) for key in ("3", "escape", "slash", "/"))


def test_navigation_keys_belong_to_the_inbox():
    zoomed, _ = step(Where(), "1", BLOCKS, ARRANGEMENT)
    assert not any(_uses(key, zoomed) for key in ("down", "up", "pagedown", "home", "tab"))


def test_a_letter_is_the_groves_only_for_a_tree_in_the_zoomed_block():
    zoomed, _ = step(Where(), "1", BLOCKS, ARRANGEMENT)
    assert _uses(letter("tars/postgres-core"), zoomed)
    assert not _uses("j", zoomed)
    assert not _uses("j")


def test_enter_belongs_to_the_inbox_and_a_letter_after_0_to_the_grove():
    assert not _uses("enter")
    assert not _uses("enter", Where(block="1", tree="a"))
    assert _uses("b", Where(block="1", tree="a", number="0"))
