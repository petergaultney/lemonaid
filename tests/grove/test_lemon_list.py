import dataclasses

from lemonaid.grove.draw import canvas, colors, lemon_list
from lemonaid.inbox.tui.rows import backend_indicators

from .shared import lemon, tree


def test_a_trees_first_lemon_keeps_its_letter_however_many_join_it():
    for count in (1, 2, 5):
        grown = tree("t", *(lemon(f"claude:{i}") for i in range(count)))
        assert lemon_list.key(grown, "t", 0) == "t"


def test_the_rest_are_a_dot_the_letter_and_their_place():
    twelve = tree("t", *(lemon(f"claude:{i}") for i in range(12)))
    keys = [lemon_list.key(twelve, "t", i) for i in range(12)]
    assert keys[1:4] == [".t1", ".t2", ".t3"]
    assert keys[9:] == [".t9", ".t0a", ".t0b"]


def _row(lemon, flipped=False):
    picture = canvas.blank(lemon_list.WIDTH + 2, 4)
    lemon_list.draw(
        picture, 0, 0, tree("t", lemon), "t", "#6495ed", 0.0, None, False, flipped=flipped
    )
    return canvas.plain_lines(picture)[1]


def test_a_row_names_the_session_then_its_wordybin_and_age():
    wordy = dataclasses.replace(
        lemon("claude:a", "FilmyBoy", "review"),
        name="REVIEW #411 grove context colors and much more",
        context="100%",
        age="1d ago",
    )
    row = _row(wordy)
    assert "REVIEW #411 grove context" in row and "Opus" not in row and "100%" not in row
    assert "review" not in row.replace("REVIEW", "")
    assert "FilmyBoy    1d" in row
    assert len(row) <= lemon_list.WIDTH


def test_a_status_that_asks_for_the_user_is_named_beside_the_session():
    blocked = dataclasses.replace(lemon("claude:a", "FilmyBoy", "blocked"), name="x" * 40)
    assert "x blocked FilmyBoy" in _row(blocked)
    assert "review" not in _row(dataclasses.replace(blocked, status="review"))


def test_a_pinned_row_marks_the_lists_border_and_leaves_its_columns_alone():
    pinned = dataclasses.replace(lemon("claude:a"), pinned=True, age="4m ago")
    assert _row(pinned).startswith("▐ t") and _row(pinned).endswith("4m │")


def test_flipped_a_row_says_where_which_model_and_its_context():
    placed = dataclasses.replace(
        lemon("claude:a", "FilmyBoy"),
        model="Sonnet 5.5",
        branch="grove/show-more",
        cwd="/work/grove-show-more",
        prs=(("411", "https://github.com/o/r/pull/411"),),
        age="4m ago",
        context="41%",
    )
    row = _row(placed, flipped=True)
    assert row.index("#411 show-more") < row.index("Sonnet 5.5") < row.index(" 41%")
    assert "4m" not in row
    assert "FilmyBoy" not in row and "lemon claude:a" not in row


def test_flipped_a_rows_pr_number_and_branch_take_the_inboxs_colors():
    placed = dataclasses.replace(
        lemon("claude:a"), branch="show-more", prs=(("411", "https://github.com/o/r/pull/411"),)
    )
    picture = canvas.blank(lemon_list.WIDTH + 2, 4)
    lemon_list.draw(
        picture, 0, 0, tree("t", placed), "t", "#6495ed", 0.0, None, False, flipped=True
    )
    cells = {cell.char: cell for cell in picture.rows[1][10:25]}
    assert cells["4"].bold and cells["4"].fg == colors.TEXT
    assert cells["w"].fg == colors.BRANCH
    assert {cells[c].link for c in "#411"} == {"https://github.com/o/r/pull/411"}
    assert not cells["w"].link and not cells[" "].link


def test_flipped_a_rows_model_takes_its_providers_color_as_in_the_inbox():
    codex = dataclasses.replace(lemon("codex:a"), model="Sol 6.1", provider="openai")
    rows = []
    for one in (lemon("claude:a"), codex):
        picture = canvas.blank(lemon_list.WIDTH + 2, 4)
        lemon_list.draw(
            picture, 0, 0, tree("t", one), "t", "#6495ed", 0.0, None, False, flipped=True
        )
        rows.append(next(c for c in picture.rows[1] if c.char in "OS").fg)
    assert rows == [
        backend_indicators.provider_style("claude:a"),
        backend_indicators.provider_style("codex:a"),
    ]


def test_flipped_without_a_branch_a_row_names_its_directory():
    unbranched = dataclasses.replace(lemon("claude:a"), cwd="/work/scratch", age="2h ago")
    assert "scratch" in _row(unbranched, flipped=True)


def test_a_lemons_context_is_colored_as_the_inbox_colors_it():
    full, light = (
        dataclasses.replace(lemon(f"claude:{n}", n), context=c)
        for c, n in (("100%", "Full"), ("5%", "Light"))
    )
    picture = canvas.blank(lemon_list.WIDTH + 2, 5)
    lemon_list.draw(
        picture, 0, 0, tree("t", full, light), "t", "#6495ed", 0.0, None, False, flipped=True
    )
    percent = [next(c for c in row if c.char == "%") for row in picture.rows[1:3]]
    assert [c.fg for c in percent] == [colors.reading_color("100%"), colors.reading_color("5%")]
    assert colors.reading_color("100%") == "#ff3c1e"  # the inbox's red at the threshold


def test_a_lemons_dot_shows_only_while_it_has_news_or_works():
    news, read, working = (
        dataclasses.replace(lemon(f"claude:{n}", n, "merge"), unread=unread, working=working)
        for n, unread, working in (
            ("News", True, False),
            ("Read", False, False),
            ("Busy", False, True),
        )
    )
    picture = canvas.blank(lemon_list.WIDTH + 2, 6)
    lemon_list.draw(picture, 0, 0, tree("t", news, read, working), "t", "#6495ed", 0.0, None, False)
    dots = [[c.fg for c in row if c.char == "●"] for row in picture.rows[1:4]]
    assert dots == [[colors.lemon_color(news, 0.0)], [], [colors.lemon_color(working, 0.0)]]


def test_a_lemons_key_takes_its_status_color():
    merged = dataclasses.replace(lemon("claude:a", "WorthSip"), status="merge")
    picture = canvas.blank(lemon_list.WIDTH + 2, 4)
    lemon_list.draw(picture, 0, 0, tree("t", merged), "t", "#6495ed", 0.0, None, False)
    key = next(cell for cell in picture.rows[1] if cell.char == "t")
    assert key.fg == colors.status_text("merge")


def test_a_key_without_a_status_is_plain_text_not_the_blocks_color():
    picture = canvas.blank(lemon_list.WIDTH + 2, 4)
    lemon_list.draw(picture, 0, 0, tree("t", lemon("claude:a")), "t", "#e3cf65", 0.0, None, False)
    key = next(cell for cell in picture.rows[1] if cell.char == "t")
    assert key.fg == colors.TEXT


def _edited(edited):
    two = tree("t", lemon("claude:a", "FirstOne"), lemon("claude:b", "SecondOne"))
    picture = canvas.blank(lemon_list.WIDTH + 2, 5)
    lemon_list.draw(picture, 0, 0, two, "t", "#6495ed", 0.0, None, False, edited=edited(two))
    return [{cell.bg for cell in row[2 : lemon_list.WIDTH - 2]} for row in picture.rows[:3]], two


def test_an_edited_lemons_whole_row_is_marked_and_no_other():
    rows, _ = _edited(lambda t: "claude:b")
    assert len(rows[2]) == 1 and rows[2] != rows[1]
    assert colors.LEMON not in rows[0]


def test_an_edited_session_marks_the_title_and_no_row():
    rows, _ = _edited(lemon_list.session)
    assert colors.LEMON in rows[0]
    assert rows[1] == rows[2]


def test_a_list_cut_short_scrolls_to_keep_an_edited_lemon_in_view():
    six = tree("t", *(lemon(f"claude:{i}") for i in range(6)))
    for edited in range(6):
        picture = canvas.blank(lemon_list.WIDTH + 2, 6)
        lemon_list.draw(
            picture, 0, 0, six, "t", "#6495ed", 0.0, None, False, 4, edited=f"claude:{edited}"
        )
        rows = canvas.plain_lines(picture)[1:4]
        assert any(f"claude:{edited}" in row for row in rows), (edited, rows)


def test_past_0z_a_lemon_has_no_key_and_nothing_breaks():
    many = tree("t", *(lemon(f"claude:{i}") for i in range(37)))
    keys = [lemon_list.key(many, "t", i) for i in range(37)]
    assert keys[35] == ".t0z" and keys[36] == ""
    picture = canvas.blank(lemon_list.WIDTH + 2, 40)
    lemon_list.draw(picture, 0, 0, many, "t", "#6495ed", 0.0, None, True)


def test_a_four_cell_key_stays_inside_the_lists_border():
    twelve = tree("t", *(lemon(f"claude:{i}") for i in range(12)))
    picture = canvas.blank(lemon_list.WIDTH + 2, 14)
    lemon_list.draw(picture, 0, 0, twelve, "t", "#6495ed", 0.0, None, False)
    rows = canvas.plain_lines(picture)
    assert rows[11][1:5] == ".t0a" and rows[11][0] != "."


def test_a_list_widens_with_the_screen_within_its_bounds():
    assert [lemon_list.width(n) for n in (100, 180, 200, 240, 400)] == [54, 54, 60, 72, 72]


def test_a_wider_list_gives_its_extra_cells_to_the_name():
    long = dataclasses.replace(
        lemon("claude:a", "FilmyBoy"), name="REVIEW #411 grove context colors", age="4m ago"
    )
    picture = canvas.blank(74, 4)
    lemon_list.draw(picture, 0, 0, tree("t", long), "t", "#6495ed", 0.0, None, False, width=72)
    row = canvas.plain_lines(picture)[1]
    assert "REVIEW #411 grove context colors" in row and row.endswith("FilmyBoy    4m │")
