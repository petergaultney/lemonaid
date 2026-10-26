from lemonaid.grove.tui import selecting
from lemonaid.grove.tui.keys import Where

from .shared import ARRANGEMENT, BLOCKS, CORE, NOTES, press


def test_outside_select_mode_a_letter_still_jumps():
    assert press("1", NOTES)[1] == "claude:notes"


def test_a_digit_and_a_letter_choose_a_trees_first_lemon_without_jumping():
    where, channel, _ = press("tab", "1", CORE)
    assert (where.selecting, where.block, where.selected_tree) == (True, "1", CORE)
    assert (where.selected_lemon, channel) == ("claude:a", "")


def test_dollar_and_a_letter_choose_the_whole_tree():
    where, _, _ = press("tab", "1", "$", CORE)
    assert (where.selected_tree, where.selected_lemon, where.whole) == (CORE, "", False)


def test_a_dot_a_letter_and_a_place_choose_another_lemon_as_jumping_would():
    waiting, _, _ = press("tab", "1", ".", CORE)
    assert (waiting.tree, waiting.selected_tree) == (CORE, "")
    where, channel, _ = press("2", where=waiting)
    assert (where.selected_tree, where.selected_lemon, where.tree, channel) == (
        CORE,
        "codex:c",
        "",
        "",
    )


def test_a_digit_after_a_whole_tree_chooses_another_block():
    where, _, _ = press("tab", "1", "$", CORE, "2")
    assert (where.block, where.selected_tree) == ("2", "")


def test_up_and_down_move_along_the_trees_list_and_stop_at_its_ends():
    where, _, _ = press("tab", "1", CORE, "down", "down")
    assert where.selected_lemon == "codex:c"
    assert press("down", where=where)[0].selected_lemon == "codex:c"
    assert press("up", "up", "up", where=where)[0].selected_lemon == "claude:a"


def test_a_place_past_the_tree_says_so():
    where, _, _ = press("tab", "1", ".", CORE, "7")
    assert where.selected_lemon == "" and "no lemon 7" in where.note


def test_enter_or_o_jumps_to_the_choice():
    assert press("tab", "1", ".", CORE, "1", "enter")[1] == "codex:b"
    assert press("tab", "1", CORE, "o")[1] == "claude:a"
    assert press("tab", "1", "$", CORE, "enter")[1] == "claude:a"  # a tree, its first lemon


def test_enter_on_a_block_alone_asks_for_a_tree():
    where, channel, _ = press("tab", "1", "enter")
    assert channel == "" and "choose a tree" in where.note


def test_a_letter_edits_the_chosen_lemon():
    where, _, target = press("tab", "1", ".", CORE, "1", "r")
    assert (target.action, target.channel, target.name) == ("rename", "codex:b", "lemon codex:b")
    assert (where.editing, where.picked_tree, where.picked_lemon) == ("rename", "core", "codex:b")


def test_a_letter_edits_the_whole_tree_where_the_edit_can():
    _, _, target = press("tab", "1", "$", CORE, "s")
    assert (target.action, target.tree, target.channel) == ("snooze", "core", "")
    assert len(target.lemons) == 3


def test_a_one_lemon_tree_is_edited_through_its_lemon():
    _, _, target = press("tab", "1", "$", NOTES, "a")
    assert (target.action, target.channel) == ("archive", "claude:notes")


def test_c_recolors_the_chosen_trees_block():
    _, _, target = press("tab", "1", CORE, "c")
    assert (target.action, target.block, target.tree) == ("color", "oria", "")


def test_another_letter_with_a_choice_says_what_letters_do():
    where, channel, target = press("tab", "1", CORE, "x")
    assert (channel, target) == ("", None)
    assert where.selected_lemon == "claude:a" and "r s a p g c" in where.note


def test_backspace_goes_back_to_the_block_then_out_of_it():
    where, _, _ = press("tab", "1", ".", CORE, "1")
    steps = []
    for _ in range(3):
        where, _, _ = press("backspace", where=where)
        steps.append((where.block, where.selected_tree, where.selected_lemon))
    assert steps == [("1", "", ""), ("", "", ""), ("", "", "")]
    assert where.selecting


def test_backspace_from_a_trees_first_lemon_goes_back_to_the_block():
    where, _, _ = press("tab", "1", CORE, "backspace")
    assert (where.block, where.selected_tree) == ("1", "")


def test_a_digit_after_a_lemon_chooses_another_block():
    where, _, _ = press("tab", "1", CORE, "2")
    assert (where.block, where.selected_tree, where.selecting) == ("2", "", True)


def test_escape_or_the_select_key_leaves_select_mode_in_the_same_block():
    for leave in ("escape", "tab"):
        where, _, _ = press("tab", "1", CORE, leave)
        assert (where.selecting, where.block, where.selected_tree) == (False, "1", "")


def test_the_select_key_is_configurable():
    where, _, _ = selecting.step(Where(), "`", BLOCKS, ARRANGEMENT, "`")
    assert where.selecting
    where, _, _ = selecting.step(Where(), "tab", BLOCKS, ARRANGEMENT, "`")
    assert not where.selecting


def test_a_search_in_select_mode_chooses_its_match():
    where, channel, _ = press("tab", "/", "W", "a", "g", "enter")
    assert channel == ""
    assert (where.selecting, where.block, where.selected_tree, where.selected_lemon) == (
        True,
        "1",
        CORE,
        "codex:b",
    )


def test_escape_from_a_search_stays_in_select_mode():
    where, _, _ = press("tab", "/", "x", "escape")
    assert (where.selecting, where.search) == (True, None)


def test_choosing_a_tree_by_click_replaces_the_choice_and_edits_nothing():
    where, _, _ = press("tab", "1", ".", CORE, "1")
    chosen = selecting.choose_tree(where, NOTES, BLOCKS, ARRANGEMENT)
    assert (chosen.selected_tree, chosen.selected_lemon, chosen.editing) == (
        NOTES,
        "claude:notes",
        "",
    )
