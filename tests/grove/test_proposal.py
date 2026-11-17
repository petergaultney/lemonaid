import copy

import pytest

from lemonaid.grove.layout import arrange, edit, proposal
from tests.grove.shared import NOW, block, plot_data, stream_saved, tree

_BLOCKS = (block("a", "1", tree("t"), tree("u")), block("b", "2", tree("v")))


def _saved() -> dict:
    raw = stream_saved({"a": plot_data(2, 2, 40, 12), "b": plot_data(60, 2, 30, 10)})
    return arrange.arrange(_BLOCKS, raw, NOW)[1]


def _proposed(**plots: dict) -> dict:
    proposed = copy.deepcopy(_saved())
    proposed["plots"].update(plots)
    return proposed


def _spot(layout: dict, group: str, key: str) -> tuple[int, int]:
    return layout["trees"][group][key]["x"], layout["trees"][group][key]["y"]


def test_shared_plots_take_the_proposed_place_and_unmoved_trees_move_with_them():
    proposed = _proposed(a=plot_data(100, 40, 40, 12, roundness=2.0), gone=plot_data(2, 40, 20, 8))
    del proposed["plots"]["b"]

    applied = proposal.apply(_saved(), proposed, _BLOCKS)

    assert applied.layout["plots"]["a"] | {"open_since": None} == _saved()["plots"]["a"] | {
        "x": 100,
        "y": 40,
        "roundness": 2.0,
    }
    assert applied.layout["plots"]["b"] == _saved()["plots"]["b"]
    assert _spot(applied.layout, "a", "t") == _spot(_saved(), "a", "t")
    assert "gone" not in applied.layout["plots"]
    assert (applied.applied, applied.skipped, applied.kept) == (["a"], ["gone"], ["b"])


def test_a_tree_moved_in_the_proposal_stands_there():
    proposed = _proposed()
    x, y = _spot(proposed, "a", "t")
    proposed["trees"]["a"]["t"].update(x=x + 1, y=y + 1)

    applied = proposal.apply(_saved(), proposed, _BLOCKS)

    assert _spot(applied.layout, "a", "t") == (x + 1, y + 1)


def test_a_tree_moved_onto_another_is_refused_by_letter():
    proposed = _proposed()
    proposed["trees"]["a"]["t"].update(
        x=proposed["trees"]["a"]["u"]["x"], y=proposed["trees"]["a"]["u"]["y"]
    )

    with pytest.raises(edit.EditError, match="^a: tree . (can.t stand at|would be pushed)"):
        proposal.apply(_saved(), proposed, _BLOCKS)


def test_a_tree_moved_past_its_block_is_refused():
    proposed = _proposed()
    proposed["trees"]["a"]["t"].update(x=39, y=0)

    with pytest.raises(edit.EditError, match="^a: tree t can.t stand at 39,0"):
        proposal.apply(_saved(), proposed, _BLOCKS)


def test_blocks_on_each_others_ground_are_refused():
    with pytest.raises(edit.EditError, match="a and b"):
        proposal.apply(_saved(), _proposed(a=plot_data(50, 2, 40, 12)), _BLOCKS)


def test_a_block_over_the_stream_is_refused_by_name():
    with pytest.raises(edit.EditError, match="^b: A road or the stream"):
        proposal.apply(_saved(), _proposed(b=plot_data(60, 25, 30, 10)), _BLOCKS)


def test_a_block_takes_over_open_ground_it_now_covers():
    saved = _saved()
    saved["plots"]["old"] = plot_data(2, 40, 40, 12, open_since=1.0)

    applied = proposal.apply(saved, _proposed(a=plot_data(4, 40, 40, 12)), _BLOCKS)

    assert "old" not in applied.layout["plots"]
    assert applied.kept == ["old"]


@pytest.mark.parametrize("roundness", [0, float("nan"), "4"])
def test_a_plot_the_grove_could_not_draw_is_refused(roundness):
    proposed = _proposed(a=plot_data(2, 2, 40, 12, roundness=roundness))

    with pytest.raises(edit.EditError, match="^a: roundness"):
        proposal.apply(_saved(), proposed, _BLOCKS)


def test_a_rounder_plot_cannot_leave_an_unmoved_tree_off_its_ground():
    saved = _saved()
    saved["plots"]["a"].update(h=20, roundness=12.0)
    saved["trees"]["a"]["t"].update(x=5, y=1)
    saved = arrange.arrange(_BLOCKS, saved, NOW)[1]
    proposed = copy.deepcopy(saved)
    proposed["plots"]["a"]["roundness"] = 1.5

    with pytest.raises(edit.EditError, match="^a: tree t.s trunk would be off"):
        proposal.apply(saved, proposed, _BLOCKS)


def test_applying_one_block_leaves_the_others_where_the_grove_has_them():
    proposed = _proposed(a=plot_data(100, 40, 40, 12), b=plot_data(150, 40, 30, 10))

    applied = proposal.apply(_saved(), proposed, _BLOCKS, only="a")

    assert applied.layout["plots"]["a"]["x"] == 100
    assert applied.layout["plots"]["b"] == _saved()["plots"]["b"]
    assert (applied.applied, applied.skipped, applied.kept) == (["a"], [], [])


def test_one_block_is_checked_against_where_the_others_are_now():
    moved = _saved()
    moved["plots"]["b"].update(x=100, y=40)
    proposed = _proposed(a=plot_data(100, 40, 40, 12))

    with pytest.raises(edit.EditError, match="a and b"):
        proposal.apply(moved, proposed, _BLOCKS, only="a")


def test_one_block_the_grove_no_longer_has_is_refused():
    with pytest.raises(edit.EditError, match="^gone isn't in both"):
        proposal.apply(_saved(), _proposed(gone=plot_data(2, 40, 20, 8)), _BLOCKS, only="gone")


def test_one_block_whose_group_ended_is_refused_though_its_open_ground_remains():
    ended = arrange.arrange((_BLOCKS[1],), _saved(), NOW + 1)[1]

    with pytest.raises(edit.EditError, match="^a isn't in both"):
        proposal.apply(ended, _proposed(a=plot_data(100, 40, 40, 12)), (_BLOCKS[1],), only="a")


def _with_a_new_tree() -> tuple[tuple, dict, dict]:
    """The grove now, with tree n new in block a, and a proposal made before n was there."""
    proposed = _saved()
    grown = (block("a", "1", tree("t"), tree("u"), tree("n")), _BLOCKS[1])
    return grown, arrange.arrange(grown, proposed, NOW)[1], proposed


def test_a_tree_new_since_the_proposal_stays_where_it_stands():
    grown, saved, proposed = _with_a_new_tree()
    x, y = _spot(proposed, "a", "t")
    proposed["trees"]["a"]["t"].update(x=x + 1, y=y + 1)

    applied = proposal.apply(saved, proposed, grown, only="a")

    assert _spot(applied.layout, "a", "n") == _spot(saved, "a", "n")
    assert _spot(applied.layout, "a", "t") == (x + 1, y + 1)


def test_a_tree_moved_onto_one_new_since_the_proposal_is_refused():
    grown, saved, proposed = _with_a_new_tree()
    x, y = _spot(saved, "a", "n")
    proposed["trees"]["a"]["t"].update(x=x, y=y)
    letters = {k: v["letter"] for k, v in saved["trees"]["a"].items()}

    with pytest.raises(edit.EditError, match=rf"^a: tree [{letters['t']}{letters['n']}] ") as e:
        proposal.apply(saved, proposed, grown, only="a")

    assert "can't stand at" in str(e.value) or "would be pushed" in str(e.value)
