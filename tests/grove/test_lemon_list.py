import dataclasses

from lemonaid.grove.draw import canvas, colors, lemon_list

from .shared import lemon, tree


def test_keys_for_small_trees_are_a_letter_and_its_capital():
    pair = tree("t", lemon("claude:a"), lemon("claude:b"))
    assert [lemon_list.key(pair, "t", i) for i in range(2)] == ["t", "T"]


def test_keys_for_bigger_trees_are_numbered():
    three = tree("t", *(lemon(f"claude:{i}") for i in range(3)))
    assert [lemon_list.key(three, "t", i) for i in range(3)] == ["t1", "t2", "t3"]


def test_model_and_context_stay_apart():
    wordy = dataclasses.replace(
        lemon("claude:a", "FilmyBoy", "review"), model="Sonnet 5.5 extended", context="100%"
    )
    picture = canvas.blank(lemon_list.WIDTH + 2, 4)
    lemon_list.draw(picture, 0, 0, tree("t", wordy), "t", "#6495ed", 0.0, None, False)
    row = canvas.plain_lines(picture)[1]
    assert "FilmyBoy" in row and "review" in row
    assert "Sonnet 5.5 100%" in row


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
    six = tree("t", *(lemon(f"claude:{i}", f"Lemon{i}") for i in range(6)))
    for edited in range(6):
        picture = canvas.blank(lemon_list.WIDTH + 2, 6)
        lemon_list.draw(
            picture, 0, 0, six, "t", "#6495ed", 0.0, None, False, 4, edited=f"claude:{edited}"
        )
        rows = canvas.plain_lines(picture)[1:4]
        assert any(f"Lemon{edited}" in row for row in rows), (edited, rows)
