import dataclasses
import re

from rich.text import Text

from lemonaid.grove.draw import block_scene, canvas, colors
from lemonaid.grove.layout import arrange
from lemonaid.grove.tui.frame import Grove, clamp_pan, render
from lemonaid.grove.tui.keys import Where

from .shared import NOW, block, lemon, tree

BLOCKS = (
    block("oria", "1", tree("oria-hq", lead=True), tree("tars/slow-first-queries")),
    block("relay", "2", tree("git-sync-wedge", lemon("claude:wedge", "CraneFly", "blocked"))),
)
GROVE = Grove(BLOCKS, *arrange.arrange(BLOCKS, {"plots": {}, "trees": {}}, NOW))


def screen_text(where: Where) -> str:
    return "\n".join(canvas.plain_lines(render(GROVE, where, 160, 48, phase=0.5)))


def test_zoomed_out_shows_every_block_sign():
    shown = screen_text(Where())
    assert "1 ORIA" in shown and "2 RELAY" in shown


def test_the_grove_view_tags_each_tree_with_its_whole_key_and_a_block_with_its_letter():
    letter = GROVE.arrangement.trees[("relay", "git-sync-wedge")].letter
    whole = re.compile(rf"(^|\s)2{letter}(\s|$)", re.MULTILINE)
    assert whole.search(screen_text(Where()))
    assert not whole.search(screen_text(Where(block="2", digits="2")))


def test_zoomed_in_lists_session_names_and_flipped_models():
    zoomed = "\n".join(canvas.plain_lines(render(GROVE, Where(block="2"), 160, 48, 0.5)))
    flipped = "\n".join(
        canvas.plain_lines(render(GROVE, Where(block="2"), 160, 48, 0.5, flipped=True))
    )
    assert "lemon claude:wedge" in zoomed and "CraneFly" in zoomed
    assert "Opus 5.5" in flipped and "lemon claude:wedge" not in flipped


def test_the_flipped_grove_view_tags_trees_with_their_stats_not_their_names():
    flipped = "\n".join(canvas.plain_lines(render(GROVE, Where(), 160, 48, 0.5, flipped=True)))
    assert " 0/1 " in flipped and "git-sync-wedge" not in flipped


def test_a_search_with_one_block_of_matches_zooms_to_it():
    shown = screen_text(Where(search="crane"))
    assert "CraneFly" in shown and "1 match in 1 block" in shown


def test_a_zoomed_block_that_is_gone_draws_the_overview():
    assert "1 ORIA" in screen_text(Where(block="9", digits="9"))


def test_a_pane_too_small_to_draw_says_so():
    shown = "\n".join(canvas.plain_lines(render(GROVE, Where(block="1", digits="1"), 69, 6, 0.0)))
    assert "needs" in shown


def test_a_scene_drawn_directly_on_a_tiny_canvas_says_so():
    picture = canvas.blank(69, 6)
    block_scene.zoomed(picture, BLOCKS[0], GROVE.arrangement, 0.0)
    assert "needs" in canvas.plain_lines(picture)[0]


def test_a_grove_too_big_for_the_screen_pans_and_says_so():
    small = canvas.plain_lines(render(GROVE, Where(), 100, 30, 0.5))
    assert "arrows pan" in small[0]
    assert "arrows pan" not in canvas.plain_lines(render(GROVE, Where(), 400, 120, 0.5))[0]


def test_a_pan_stops_at_the_groves_edge():
    far = clamp_pan(GROVE, Where(pan=(9999, 9999)), 100, 30)
    assert 0 < far.pan[0] < 210 and 0 < far.pan[1] < 60
    assert clamp_pan(GROVE, Where(pan=(40, 8)), 400, 120).pan == (0, 0)


def _chosen() -> Where:
    letter = GROVE.arrangement.trees[("relay", "git-sync-wedge")].letter
    return Where(block="2", selecting=True, selected_tree=letter, selected_lemon="claude:wedge")


def test_select_mode_draws_the_chosen_lemons_card_beside_its_list():
    carded = dataclasses.replace(
        GROVE, cards={"claude:wedge": (Text("wedge card headline"), Text("Needs: a look"))}
    )
    shown = "\n".join(canvas.plain_lines(render(carded, _chosen(), 160, 48, 0.5)))
    hidden = "\n".join(
        canvas.plain_lines(render(carded, _chosen(), 160, 48, 0.5, card_shown=False))
    )
    assert "wedge card headline" in shown and "Needs: a look" in shown
    assert "wedge card headline" not in hidden


def test_select_mode_colors_the_screens_edges():
    picture = render(GROVE, _chosen(), 160, 48, 0.5)
    assert picture.rows[10][0].bg == picture.rows[10][-1].bg == colors.LEMON
    assert render(GROVE, Where(block="2"), 160, 48, 0.5).rows[10][0].bg != colors.LEMON


def test_a_flashed_tree_is_tinted_alert_red():
    letter = GROVE.arrangement.trees[("relay", "git-sync-wedge")].letter
    picture = render(GROVE, _chosen(), 160, 48, 0.5, flashed=("2", letter))
    tinted = [cell for row in picture.rows for cell in row if cell.target == ("2", letter)]
    assert tinted and all(cell.bg != canvas.BACKGROUND for cell in tinted)
    plain = render(GROVE, _chosen(), 160, 48, 0.5)
    assert [c.bg for row in plain.rows for c in row if c.target == ("2", letter)] != [
        c.bg for c in tinted
    ]


def test_select_mode_tags_each_tree_with_the_dollar_that_chooses_it_whole():
    letter = GROVE.arrangement.trees[("relay", "git-sync-wedge")].letter
    selecting = "\n".join(canvas.plain_lines(render(GROVE, _chosen(), 160, 48, 0.5)))
    jumping = "\n".join(canvas.plain_lines(render(GROVE, Where(block="2"), 160, 48, 0.5)))
    assert f"${letter}" in selecting and f"${letter}" not in jumping


def test_the_jump_mode_hints_name_the_configured_select_key():
    for where in (Where(), Where(block="2", digits="2")):
        shown = "\n".join(canvas.plain_lines(render(GROVE, where, 160, 48, 0.5, select_key="f6")))
        assert "F6 selects" in shown and "Tab selects" not in shown
