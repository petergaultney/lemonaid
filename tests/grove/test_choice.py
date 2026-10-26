import dataclasses

from lemonaid.grove.tui import choice

from .selecting.shared import ARRANGEMENT, BIG, BLOCKS, CORE, LOOSE, OTHER, press
from .shared import block


def test_a_chosen_lemon_that_went_leaves_its_tree_chosen():
    where, _, _ = press("tab", "1", ".", CORE, "2")
    fewer = dataclasses.replace(BIG, lemons=BIG.lemons[:2])
    after = (block("oria", "1", fewer, LOOSE), block("relay", "2", OTHER))
    found = choice.reconcile(where, after, ARRANGEMENT)
    assert (found.selected_tree, found.selected_lemon) == (CORE, "")


def test_a_chosen_tree_that_went_is_let_go():
    where, _, _ = press("tab", "1", CORE)
    after = (block("oria", "1", LOOSE), block("relay", "2", OTHER))
    found = choice.reconcile(where, after, ARRANGEMENT)
    assert (found.selecting, found.block, found.selected_tree) == (True, "1", "")


def test_a_choice_still_there_stays():
    where, _, _ = press("tab", "1", CORE)
    assert choice.reconcile(where, BLOCKS, ARRANGEMENT) == where
