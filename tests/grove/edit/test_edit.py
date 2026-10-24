import pytest

from lemonaid.grove.layout import edit

SAVED = {
    "plots": {
        "relay": {"x": 10, "y": 5, "w": 40, "h": 12, "roundness": 3.4, "open_since": None},
        "gone": {"x": 60, "y": 5, "w": 30, "h": 9, "roundness": 2.4, "open_since": 1.0},
    },
    "trees": {"relay": {"a": {"x": 5, "y": 3}}, "gone": {"b": {"x": 1, "y": 1}}},
}


def test_move_changes_only_the_named_plot_and_leaves_its_input_alone():
    moved = edit.move(SAVED, "relay", 70, 30)
    assert moved["plots"]["relay"]["x"] == 70 and moved["plots"]["relay"]["y"] == 30
    assert SAVED["plots"]["relay"]["x"] == 10
    assert moved["trees"] == SAVED["trees"]


def test_resize_and_reshape():
    changed = edit.reshape(edit.resize(SAVED, "relay", 50, 14), "relay", 8)
    assert (changed["plots"]["relay"]["w"], changed["plots"]["relay"]["h"]) == (50, 14)
    assert changed["plots"]["relay"]["roundness"] == 8


@pytest.mark.parametrize(
    "change",
    [
        lambda s: edit.move(s, "relay", -1, 0),
        lambda s: edit.resize(s, "relay", 5, 5),
        lambda s: edit.reshape(s, "relay", 20),
        lambda s: edit.move(s, "nowhere", 1, 1),
        lambda s: edit.reframe(s, "relay", 0, 0, 11, 9),
        lambda s: edit.place_tree(s, "relay", "nowhere", False, 1, 1),
    ],
)
def test_bad_edits_are_refused(change):
    with pytest.raises(edit.EditError):
        change(SAVED)


def test_clear_open_drops_open_ground_and_its_trees():
    cleared, names = edit.clear_open(SAVED)
    assert names == ["gone"]
    assert "gone" not in cleared["plots"] and "gone" not in cleared["trees"]
    assert "relay" in cleared["plots"]


def test_rename_tree_keeps_its_spot_and_letter_under_the_new_key():
    renamed = edit.rename_tree(SAVED, "relay", "a", "b")
    assert renamed["trees"]["relay"] == {"b": {"x": 5, "y": 3}}
    shared = edit.share_tree(SAVED, "relay", "a", "b")
    assert shared["trees"]["relay"] == {"a": {"x": 5, "y": 3}, "b": {"x": 5, "y": 3}}
    assert SAVED["trees"]["relay"] == {"a": {"x": 5, "y": 3}}


def test_reframing_from_the_left_keeps_trees_where_they_stand_on_the_ground():
    changed = edit.reframe(SAVED, "relay", 6, 5, 44, 12)
    assert (changed["plots"]["relay"]["x"], changed["plots"]["relay"]["w"]) == (6, 44)
    assert changed["trees"]["relay"]["a"] == {"x": 9, "y": 3}


def test_a_block_made_smaller_pushes_the_trees_it_cuts_off_back_onto_it():
    saved = {
        "plots": {"relay": {"x": 10, "y": 5, "w": 40, "h": 12}},
        "trees": {
            "relay": {
                "inside": {"letter": "a", "x": 8, "y": 4, "w": 10, "h": 6, "top": 2},
                "edge": {"letter": "b", "x": 30, "y": 8, "w": 10, "h": 6, "top": 2},
                "wide": {"letter": "c", "x": 20, "y": 3, "w": 36, "h": 6, "top": 2},
            }
        },
    }
    spots = edit.resize(saved, "relay", 32, 9)["trees"]["relay"]
    assert spots["inside"] == saved["trees"]["relay"]["inside"]
    assert (spots["edge"]["x"], spots["edge"]["y"]) == (27, 5)  # the least that puts it on
    assert spots["wide"] == {"letter": "c", "squeeze": True}  # too wide, so it stands afresh


def test_placing_the_lead_moves_its_lead_spot_and_leaves_its_own():
    saved = {**SAVED, "trees": {"relay": {"a": {"x": 5, "y": 3}, ":lead": {"x": 2, "y": 2}}}}
    led = edit.place_tree(saved, "relay", "a", True, 20, 6)["trees"]["relay"]
    assert led == {"a": {"x": 5, "y": 3}, ":lead": {"x": 20, "y": 6}}
    assert edit.place_tree(saved, "relay", "a", False, 7, 4)["trees"]["relay"]["a"] == {
        "x": 7,
        "y": 4,
    }
