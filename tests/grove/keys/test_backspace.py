from lemonaid.grove.tui.keys import Where, uses

from .test_step import ARRANGEMENT, BIG, BLOCKS, letter, press


def test_backspace_clears_a_typed_dotted_key_but_stays_in_the_block():
    where, _ = press("1", ".", letter(BIG.key), "backspace")
    assert (where.block, where.dot, where.tree, where.number) == ("1", False, "", "")


def test_backspace_clears_a_dot_waiting_for_its_letter():
    where, _ = press("1", ".", "backspace")
    assert (where.block, where.dot) == ("1", False)


def test_backspace_in_a_block_with_nothing_typed_returns_to_the_grove():
    where, _ = press("1", "backspace")
    assert where == Where()


def test_backspace_returns_from_a_two_digit_block():
    where, _ = press("1", "0", "backspace")
    assert where == Where()


def test_backspace_keeps_the_pan_and_does_nothing_at_rest():
    panned = Where(pan=(3.0, 4.0))
    assert press("backspace", where=panned)[0] == panned


def test_the_grove_uses_backspace():
    assert uses(Where(block="1", digits="1"), "backspace", BLOCKS, ARRANGEMENT)
