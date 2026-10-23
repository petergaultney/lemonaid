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
