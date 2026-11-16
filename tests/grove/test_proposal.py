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
