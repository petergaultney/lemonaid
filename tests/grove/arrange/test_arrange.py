import dataclasses

from lemonaid.grove.layout import new_spots
from lemonaid.grove.layout.arrange import arrange

from ..shared import DAY, NOW, block, lemon, tree

EMPTY = {"plots": {}, "trees": {}}


def test_a_second_arrangement_keeps_every_plot_spot_and_letter():
    blocks = (
        block("oria", "1", tree("a-core"), tree("b-ops")),
        block("relay", "2", tree("c-wedge")),
    )
    first, saved = arrange(blocks, EMPTY, NOW)
    second, _ = arrange(blocks, saved, NOW + 60)
    assert first == second


def test_a_new_sibling_does_not_move_or_reletter_a_tree():
    before, saved = arrange((block("oria", "1", tree("a-core")),), EMPTY, NOW)
    after, _ = arrange((block("oria", "1", tree("a-core"), tree("a-cache")),), saved, NOW + 60)
    old, new = before.trees[("oria", "a-core")], after.trees[("oria", "a-core")]
    assert (old.cx, old.cy, old.letter) == (new.cx, new.cy, new.letter)


def test_the_lead_tree_reads_l_whatever_letter_it_was_given():
    found, _ = arrange((block("oria", "1", tree("hq", lead=True)),), EMPTY, NOW)
    assert found.trees[("oria", "hq")].letter == "l"


ROOMY = {
    "plots": {
        "g": {"x": 10, "y": 5, "w": 90, "h": 30, "roundness": 4.5, "seed": 3, "texture": "rows"}
    },
    "trees": {},
}


def test_a_new_tree_takes_the_oldest_free_spot():
    trees = [tree(name) for name in ("one", "two", "three")]
    _, saved = arrange((block("g", "1", *trees),), ROOMY, NOW)
    _, saved = arrange((block("g", "1", trees[1], trees[2]),), saved, NOW + DAY)  # one goes first
    _, saved = arrange((block("g", "1", trees[2]),), saved, NOW + 2 * DAY)  # then two
    one = (saved["trees"]["g"]["one"]["x"], saved["trees"]["g"]["one"]["y"])
    found, _ = arrange((block("g", "1", trees[2], tree("four")),), saved, NOW + 3 * DAY)
    four = found.trees[("g", "four")]
    assert (four.cx, four.cy) == one


def test_a_new_group_takes_the_open_ground_an_ended_group_left():
    _, saved = arrange(
        (block("ending", "1", tree("x")), block("staying", "2", tree("y"))), EMPTY, NOW
    )
    left_behind = saved["plots"]["ending"]
    found, saved = arrange(
        (block("staying", "1", tree("y")), block("new", "2", tree("z"))), saved, NOW + DAY
    )
    assert (found.plots["new"].x, found.plots["new"].y) == (left_behind["x"], left_behind["y"])
    assert "ending" not in saved["plots"]


def test_a_group_with_no_live_lemons_leaves_open_ground():
    _, saved = arrange(
        (block("ending", "1", tree("x")), block("staying", "2", tree("y"))), EMPTY, NOW
    )
    found, _ = arrange((block("staying", "1", tree("y")),), saved, NOW + DAY)
    assert len(found.open) == 1


def test_younger_trees_are_drawn_smaller():
    young = dataclasses.replace(
        tree("young"), lemons=(dataclasses.replace(tree("young").lemons[0], born=NOW - 3600),)
    )
    found, _ = arrange((block("g", "1", tree("old"), young),), EMPTY, NOW)
    assert found.trees[("g", "young")].size < found.trees[("g", "old")].size


def test_a_returning_group_keeps_its_plot_when_a_new_group_arrives_with_it():
    _, saved = arrange((block("returning", "1", tree("r")),), EMPTY, NOW)
    before = saved["plots"]["returning"]
    _, saved = arrange((), saved, NOW + DAY)
    found, _ = arrange(
        (block("new", "1", tree("n")), block("returning", "2", tree("r"))), saved, NOW + 2 * DAY
    )
    assert (found.plots["returning"].x, found.plots["returning"].y) == (before["x"], before["y"])


def test_a_returning_tree_keeps_its_spot_when_an_older_new_tree_arrives_with_it():
    anchor, returning = tree("anchor"), tree("returning")
    _, saved = arrange((block("g", "1", anchor, returning),), EMPTY, NOW)
    before = dict(saved["trees"]["g"]["returning"])
    _, saved = arrange((block("g", "1", anchor),), saved, NOW + DAY)
    found, _ = arrange(
        (block("g", "1", anchor, tree("older-newcomer"), returning),), saved, NOW + 2 * DAY
    )
    spot = found.trees[("g", "returning")]
    assert (spot.cx, spot.cy, spot.letter) == (before["x"], before["y"], before["letter"])


def test_a_tree_saved_with_the_lead_letter_gets_another_once_it_is_not_the_lead():
    saved = {"plots": {}, "trees": {"oria": {"hq": {"x": 10, "y": 5, "letter": "l"}}}}
    found, _ = arrange((block("oria", "1", tree("hq")),), saved, NOW)
    assert found.trees[("oria", "hq")].letter not in ("l", "")


def test_trees_grow_no_further_than_keeps_them_clear_of_each_other():
    trees = [tree(f"t{i}") for i in range(6)]
    found, _ = arrange((block("g", "1", *trees),), EMPTY, NOW)
    sizes_seen = [found.trees[("g", t.key)].size for t in trees]
    assert max(sizes_seen) <= 1.6 and min(sizes_seen) >= 0.45


WITH_HOUSE = {
    "plots": {
        "west": {"x": 10, "y": 5, "w": 90, "h": 30, "roundness": 4.5, "seed": 3, "texture": "rows"},
        "g": {"x": 10, "y": 5, "w": 90, "h": 30, "roundness": 4.5, "seed": 3, "texture": "rows"},
        "": {"x": 140, "y": 15, "w": 24, "h": 7, "roundness": 12.0, "seed": 0, "texture": "house"},
    },
    "trees": {},
}


def test_a_lead_stands_on_the_side_nearest_the_packhouse():
    blocks = (
        block("west", "1", tree("one"), tree("two"), tree("head", lead=True)),
        block("", "0", tree("hq")),
    )
    found, _ = arrange(blocks, WITH_HOUSE, NOW)
    west, house = found.plots["west"], found.plots[""]
    head = found.trees[("west", "head")]
    others = [found.trees[("west", k)] for k in ("one", "two")]
    toward_house = 1 if house.x > west.x else -1
    assert all(toward_house * (head.cx - o.cx) > 0 for o in others)


def test_a_tree_that_stops_leading_goes_back_to_its_own_spot():
    leading = (block("g", "1", tree("a", lead=True), tree("b")), block("", "0", tree("hq")))
    found, saved = arrange(leading, WITH_HOUSE, NOW)
    own = saved["trees"]["g"]["a"]
    following = (block("g", "1", tree("a"), tree("b", lead=True)), block("", "0", tree("hq")))
    after, _ = arrange(following, saved, NOW + 60)
    assert (after.trees[("g", "a")].cx, after.trees[("g", "a")].cy) == (own["x"], own["y"])
    assert (after.trees[("g", "b")].cx, after.trees[("g", "b")].cy) == (
        found.trees[("g", "a")].cx,
        found.trees[("g", "a")].cy,
    )


def test_a_crowded_neighbor_shrinks_rather_than_moving():
    trees = [tree(f"t{i}") for i in range(5)]
    before, saved = arrange((block("g", "1", *trees),), EMPTY, NOW)
    grown = [tree("t0", *(lemon(f"claude:t0-{i}") for i in range(5))), *trees[1:]]
    after, _ = arrange((block("g", "1", *grown),), saved, NOW + 1)
    for t in trees[1:]:
        old, new = before.trees[("g", t.key)], after.trees[("g", t.key)]
        assert (old.cx, old.cy) == (new.cx, new.cy)


def test_a_session_named_like_the_old_lead_marker_has_a_spot_of_its_own():
    blocks = (
        block("g", "1", tree("head", lead=True), tree("~lead"), tree(":x")),
        block("", "0", tree("hq")),
    )
    found, _ = arrange(blocks, WITH_HOUSE, NOW)
    spots = {(found.trees[("g", k)].cx, found.trees[("g", k)].cy) for k in ("head", "~lead", ":x")}
    assert len(spots) == 3


def test_a_tree_shows_the_name_given_to_its_main_lemon():
    given = dataclasses.replace(lemon("claude:x"), name="review the 837 PR", named=True)
    derived = lemon("claude:y")
    found, _ = arrange(
        (block("g", "1", tree("edi/transform-qa", given), tree("edi/other", derived)),), EMPTY, NOW
    )
    assert found.trees[("g", "edi/transform-qa")].label == "review the 837 PR"
    assert found.trees[("g", "edi/other")].label == "other"


def test_a_saved_capital_letter_is_picked_again_in_lowercase():
    named = dataclasses.replace(lemon("claude:x"), name="Stray inbox cards", named=True)
    saved = {"plots": {}, "trees": {"g": {"stray": {"x": 10, "y": 5, "letter": "S"}}}}
    found, _ = arrange((block("g", "1", tree("stray", named)),), saved, NOW)
    assert found.trees[("g", "stray")].letter == "s"


def test_two_trees_saved_with_one_letter_end_up_with_two():
    saved = {
        "plots": {},
        "trees": {
            "g": {"a": {"x": 10, "y": 5, "letter": "q"}, "b": {"x": 30, "y": 5, "letter": "q"}}
        },
    }
    found, _ = arrange((block("g", "1", tree("a"), tree("b")),), saved, NOW)
    letters = [found.trees[("g", k)].letter for k in ("a", "b")]
    assert len(set(letters)) == 2 and all(
        letter in "abcdefghijklmnopqrstuvwxyz" for letter in letters
    )


def test_trees_saved_on_one_spot_come_apart_keeping_their_letters():
    first, saved = arrange(
        (block("g", "1", tree("a"), tree("b")),), {"plots": {}, "trees": {}}, NOW
    )
    spots = saved["trees"]["g"]
    spots["b"].update(x=spots["a"]["x"], y=spots["a"]["y"])  # as a layout saved before the fix
    found, _ = arrange((block("g", "1", tree("a"), tree("b")),), saved, NOW + 60)
    a, b = found.trees[("g", "a")], found.trees[("g", "b")]
    assert (a.cx, a.cy) == (first.trees[("g", "a")].cx, first.trees[("g", "a")].cy)
    assert (b.cx, b.cy) != (a.cx, a.cy)
    assert b.letter == first.trees[("g", "b")].letter


def test_a_block_that_outgrows_its_plot_grows_into_free_ground_beside_it():
    first, saved = arrange((block("g", "1", tree("a")),), {"plots": {}, "trees": {}}, NOW)
    small = first.plots["g"]
    crowd = block("g", "1", *(tree(k) for k in "abcdefgh"))
    found, _ = arrange((crowd,), saved, NOW + 60)
    plot = found.plots["g"]
    assert plot.w * plot.h > small.w * small.h
    for t in crowd.trees:
        s = found.trees[("g", t.key)]
        assert 0 <= s.cx <= plot.w and 0 <= s.cy <= plot.h, t.key


def test_a_stump_keeps_its_trees_name_for_two_hours():
    _, saved = arrange(
        (block("g", "1", tree("a"), tree("going")),), {"plots": {}, "trees": {}}, NOW
    )
    soon, saved = arrange((block("g", "1", tree("a")),), saved, NOW + 60)
    later, _ = arrange((block("g", "1", tree("a")),), saved, NOW + 3 * 3600)
    assert [s.label for s in soon.stumps["g"]] == ["going"]
    assert [s.label for s in later.stumps["g"]] == [""]


def test_a_tree_saved_off_its_full_block_stands_inside_it_again():
    def plot(x, y, w, h):
        return {"x": x, "y": y, "w": w, "h": h, "roundness": 2.4, "seed": 65, "texture": "rows"}

    big = tree("jump", *(lemon(f"claude:jump-{i}") for i in range(4)))
    others = [tree(key) for key in ("browser", "focused", "freeze", "restart")]
    spots = {"browser": (9, 9), "focused": (9, 15), "freeze": (40, 6), "restart": (31, 15)}
    saved = {
        # Block 5 boxed in: another block just below it, and one on each side.
        "plots": {
            "lemonaid": plot(37, 21, 57, 24),
            "below": plot(37, 47, 57, 13),
            "left": plot(1, 21, 34, 24),
            "right": plot(96, 21, 30, 24),
            "above": plot(37, 1, 57, 18),
        },
        "trees": {
            "lemonaid": {
                **{key: {"x": x, "y": y, "letter": key[0]} for key, (x, y) in spots.items()},
                "jump": {"x": 28, "y": 27, "letter": "s"},  # below the block's bottom edge
            }
        },
    }
    blocks = (
        block("lemonaid", "5", *others, big),
        *(
            block(name, str(i), tree(f"{name}-tree"))
            for i, name in enumerate(("below", "left", "right", "above"), start=1)
        ),
    )
    found, _ = arrange(blocks, saved, NOW)
    s, p = found.trees[("lemonaid", "jump")], found.plots["lemonaid"]
    assert 0 <= s.cx <= p.w and 0 <= s.cy <= p.h, (s.cx, s.cy, p.w, p.h)


def _plot(x, y, w, h, **more):
    return {"x": x, "y": y, "w": w, "h": h, "roundness": 4.5, "seed": 3, "texture": "rows", **more}


_LARGE = tree("large", *(lemon(f"claude:large-{i}") for i in range(5)))


def _fits(found, name, t):
    s, p = found.trees[(name, t.key)], found.plots[name]
    w, h, top = new_spots.footprint(t, s.label, s.letter, s.size)
    x, y = s.cx - w // 2, s.cy - top
    return x >= 0 and s.cy >= 0 and x + w <= p.w and y + h <= p.h  # its crown may rise above


def test_a_block_too_short_for_its_tree_grows_taller_not_wider():
    saved = {"plots": {"g": _plot(40, 20, 40, 8)}, "trees": {}}
    found, _ = arrange((block("g", "1", _LARGE),), saved, NOW)
    assert found.plots["g"].w == 40 and found.plots["g"].h > 8
    assert _fits(found, "g", _LARGE)


def test_a_tree_taller_than_its_block_lets_its_crown_rise_above_it():
    saved = {"plots": {"g": _plot(40, 20, 40, 16)}, "trees": {}}
    found, _ = arrange((block("g", "1", _LARGE),), saved, NOW)
    assert (found.plots["g"].w, found.plots["g"].h) == (40, 16)
    assert _fits(found, "g", _LARGE)


def test_a_block_grows_over_open_ground_and_the_open_ground_is_forgotten():
    open_ = {"open_since": 1.0}
    saved = {
        "plots": {
            "g": _plot(40, 20, 40, 9),
            "left": _plot(1, 20, 37, 9, **open_),
            "right": _plot(82, 20, 40, 9, **open_),
            "above": _plot(40, 1, 40, 17, **open_),
            "below": _plot(40, 31, 40, 20, **open_),
        },
        "trees": {},
    }
    found, kept = arrange((block("g", "1", _LARGE),), saved, NOW)
    assert _fits(found, "g", _LARGE)
    grown = found.plots["g"]
    for name, p in kept["plots"].items():
        if name != "g":
            assert not (
                p["x"] < grown.x + grown.w
                and grown.x < p["x"] + p["w"]
                and p["y"] < grown.y + grown.h
                and grown.y < p["y"] + p["h"]
            ), name


def test_a_lead_saved_off_its_block_stands_on_it_again():
    head = tree("head", lead=True)
    saved = {
        "plots": {"g": _plot(30, 20, 40, 20), "": {**_plot(100, 20, 24, 9), "texture": "house"}},
        "trees": {
            "g": {
                "head": {"x": 20, "y": 10, "letter": "h"},
                ":lead": {"x": 20, "y": 25, "letter": "l", "w": 10, "h": 12, "top": 5},
            }
        },
    }
    found, kept = arrange((block("g", "1", head), block("", "0", tree("hq"))), saved, NOW)
    assert _fits(found, "g", head)
    again, _ = arrange((block("g", "1", head), block("", "0", tree("hq"))), kept, NOW + 60)
    assert (again.trees[("g", "head")].cx, again.trees[("g", "head")].cy) == (
        found.trees[("g", "head")].cx,
        found.trees[("g", "head")].cy,
    )
