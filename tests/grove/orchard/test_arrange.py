from lemonaid.grove.layout import arrange, labels, orchard
from lemonaid.grove.source import lemon_trees

from ..shared import NOW, block, lemon, tree


def _trees_scale(found, saved):
    return arrange.arrange(lemon_trees.one_per_lemon(found), orchard.with_scale(saved, True), NOW)


def test_a_session_s_main_lemon_keeps_its_letter_from_blocks_scale_and_each_lemon_gets_one():
    found = (block("g", "1", tree("lead", lead=True), tree("work", lemon("a:1"), lemon("b:2"))),)
    _, blocks_scale = arrange.arrange(found, {"plots": {}, "trees": {}}, NOW)
    work = blocks_scale["trees"]["g"]["work"]["letter"]

    laid_out, _ = _trees_scale(found, blocks_scale)

    assert laid_out.plots["g"].texture == "orchard"
    assert laid_out.trees[("g", "lead")].letter == labels.LEAD_LETTER
    assert laid_out.trees[("g", "work")].letter == work
    assert laid_out.trees[("g", "b:2")].letter not in ("", work, labels.LEAD_LETTER)


def test_a_new_group_takes_the_room_a_gone_one_left():
    one, two = block("one", "1", tree("a")), block("two", "2", tree("b"))
    _, saved = _trees_scale((one, two), {"plots": {}, "trees": {}})
    gone = saved["plots"]["one"]

    _, saved = arrange.arrange(lemon_trees.one_per_lemon((two,)), saved, NOW + 60)  # gone

    laid_out, _ = arrange.arrange(
        lemon_trees.one_per_lemon((two, block("three", "3", tree("c")))), saved, NOW + 3 * 86400
    )

    assert (laid_out.plots["three"].x, laid_out.plots["three"].y) == (gone["x"], gone["y"])
