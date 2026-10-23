import dataclasses

from lemonaid.grove.layout import arrange
from lemonaid.grove.tui import picking
from lemonaid.grove.tui.keys import Where

from ..shared import NOW, block, lemon, tree


def _in(session: str, *lemons):
    return tree(session, *(dataclasses.replace(m, session=session) for m in lemons))


BIG = _in("core", lemon("claude:a", "SwordAce"), lemon("codex:b", "WagonCoy"), lemon("codex:c"))
LOOSE = tree("/work/notes", lemon("claude:notes"))
BLOCKS = (block("oria", "1", BIG, LOOSE),)
ARRANGEMENT, _ = arrange.arrange(BLOCKS, {"plots": {}, "trees": {}}, NOW)
CORE = ARRANGEMENT.trees[("oria", "core")].letter
NOTES = ARRANGEMENT.trees[("oria", "/work/notes")].letter


def press(*typed: str, where: Where | None = None):
    where, channel, rename = where or Where(), "", None
    for key in typed:
        where, channel, rename = picking.step(where, key, BLOCKS, ARRANGEMENT)
    return where, channel, rename


def test_alt_and_a_letter_picks_the_whole_tree_without_jumping():
    where, channel, _ = press("1", f"alt+{CORE}")
    assert (where.picked_tree, where.picked_lemon, channel) == ("core", "", "")


def test_alt_and_the_capital_picks_the_second_lemon():
    assert press("1", f"alt+shift+{CORE}")[0].picked_lemon == "codex:b"


def test_a_digit_picks_one_lemon_on_the_picked_tree():
    assert press("1", f"alt+{CORE}", "3")[0].picked_lemon == "codex:c"


def test_r_asks_to_rename_the_session_from_its_current_name():
    where, _, rename = press("1", f"alt+{CORE}", "r")
    assert rename == picking.Rename(
        ("oria",), "core", "", "core", (("claude:a", ""), ("codex:b", ""), ("codex:c", ""))
    )
    assert where.picked_tree == "core"


def test_r_on_a_picked_lemon_asks_to_rename_it_from_its_name():
    _, _, rename = press("1", f"alt+{CORE}", "2", "r")
    assert (rename.channel, rename.name) == ("codex:b", "lemon codex:b")


def test_a_tree_that_is_not_a_tmux_session_cannot_be_renamed():
    where, _, rename = press("1", f"alt+{NOTES}", "r")
    assert rename is None and "tmux session" in where.note


def test_escape_lets_go_of_the_pick():
    where, _, _ = press("1", f"alt+{CORE}")
    assert press("escape", where=where)[0].picked_tree == ""


def test_enter_on_a_pick_jumps_to_it():
    assert press("1", f"alt+shift+{CORE}", "enter")[1] == "codex:b"


def test_alt_before_zooming_says_to_pick_a_block():
    where, _, _ = press(f"alt+{CORE}")
    assert where.picked_tree == "" and "block number" in where.note


TEN = _in("ten", *(lemon(f"claude:{i}") for i in range(1, 11)))
TEN_BLOCKS = (block("big", "1", TEN),)
TEN_ARRANGEMENT, _ = arrange.arrange(TEN_BLOCKS, {"plots": {}, "trees": {}}, NOW)


def test_lemon_ten_and_later_can_be_picked_and_renamed():
    where, rename = Where(), None
    letter = TEN_ARRANGEMENT.trees[("big", "ten")].letter
    for key in ("1", f"alt+{letter}", "1", "0", "r"):
        where, _, rename = picking.step(where, key, TEN_BLOCKS, TEN_ARRANGEMENT)
    assert rename.channel == "claude:10"


def test_a_digit_that_cannot_extend_the_number_starts_a_new_one():
    where = Where()
    letter = TEN_ARRANGEMENT.trees[("big", "ten")].letter
    for key in ("1", f"alt+{letter}", "1", "7"):
        where, _, _ = picking.step(where, key, TEN_BLOCKS, TEN_ARRANGEMENT)
    assert (where.picked_lemon, where.number) == ("claude:7", "")


def test_a_session_rename_covers_its_trees_in_every_group():
    shared = (
        block("a", "1", _in("old", lemon("claude:x"))),
        block("b", "2", _in("old", lemon("claude:y"))),
    )
    found, _ = arrange.arrange(shared, {"plots": {}, "trees": {}}, NOW)
    letter = found.trees[("a", "old")].letter
    where, rename = Where(), None
    for key in ("1", f"alt+{letter}", "r"):
        where, _, rename = picking.step(where, key, shared, found)
    assert rename.groups == ("a", "b")
    assert rename.lemons == (("claude:x", ""), ("claude:y", ""))
