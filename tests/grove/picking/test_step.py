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


def press(*typed: str, where: Where | None = None, blocks=BLOCKS, arrangement=ARRANGEMENT):
    where, channel, rename = where or Where(), "", None
    for key in typed:
        where, channel, rename = picking.step(where, key, blocks, arrangement)
    return where, channel, rename


def test_a_trees_letter_chooses_its_session_first_without_jumping():
    where, channel, _ = press("alt+r", "1", CORE)
    assert (where.picked_tree, where.picked_lemon, channel) == ("core", "", "")


def test_the_letter_again_or_an_arrow_moves_on_to_each_lemon_and_round():
    assert press("alt+r", "1", CORE, CORE)[0].picked_lemon == "claude:a"
    assert press("alt+r", "1", CORE, "down", "down")[0].picked_lemon == "codex:b"
    assert press("alt+r", "1", CORE, "up")[0].picked_lemon == "codex:c"
    assert press("alt+r", "1", CORE, *[CORE] * 4)[0].picked_lemon == ""


def test_enter_asks_to_rename_the_session_from_its_current_name():
    where, _, rename = press("alt+r", "1", CORE, "enter")
    assert rename == picking.Rename(
        ("oria",), "core", "", "core", (("claude:a", ""), ("codex:b", ""), ("codex:c", ""))
    )
    assert where.renaming


def test_enter_on_a_lemon_asks_to_rename_it_from_its_name():
    _, _, rename = press("alt+r", "1", CORE, CORE, CORE, "enter")
    assert (rename.channel, rename.name) == ("codex:b", "lemon codex:b")


def test_a_tree_that_is_not_a_tmux_session_offers_only_its_lemons():
    where, _, _ = press("alt+r", "1", NOTES)
    assert where.picked_lemon == "claude:notes"


def test_escape_stops_renaming():
    where, _, _ = press("alt+r", "1", CORE, "escape")
    assert (where.renaming, where.picked_tree) == (False, "")


def test_without_alt_r_a_letter_still_jumps():
    assert press("1", NOTES)[1] == "claude:notes"


def test_a_letter_before_a_block_says_to_type_one():
    where, _, _ = press("alt+r", CORE)
    assert where.picked_tree == "" and "block number" in where.note


def test_the_prompt_says_what_is_about_to_be_renamed():
    where, _, _ = press("alt+r", "1", CORE, CORE)
    assert "rename lemon SwordAce?" in picking.prompt(where, BLOCKS, CORE)


def test_a_session_rename_covers_its_trees_in_every_group():
    shared = (
        block("a", "1", _in("old", lemon("claude:x"))),
        block("b", "2", _in("old", lemon("claude:y"))),
    )
    found, _ = arrange.arrange(shared, {"plots": {}, "trees": {}}, NOW)
    letter = found.trees[("a", "old")].letter
    _, _, rename = press("alt+r", "1", letter, "enter", blocks=shared, arrangement=found)
    assert rename.groups == ("a", "b")
    assert rename.lemons == (("claude:x", ""), ("claude:y", ""))
