from lemonaid.grove.tui.keys import Where, reconcile

from ..shared import block, tree

BEFORE = (block("oria", "1", tree("a")), block("relay", "2", tree("b")))


def test_a_zoomed_block_that_ended_is_let_go():
    assert reconcile(Where(block="2", digits="2"), BEFORE, BEFORE[:1]) == Where()


def test_a_zoomed_block_whose_digit_now_names_another_group_is_let_go():
    after = (block("relay", "1", tree("b")), block("misc", "2", tree("c")))
    assert reconcile(Where(block="2", digits="2"), BEFORE, after) == Where()


def test_a_zoomed_block_that_stays_stays_zoomed():
    where = Where(block="2", digits="2")
    assert reconcile(where, BEFORE, BEFORE) == where


def test_a_search_survives_its_block_ending():
    assert reconcile(Where(block="2", search="crane"), BEFORE, BEFORE[:1]).search == "crane"
