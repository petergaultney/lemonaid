import dataclasses

from lemonaid.grove.draw import canvas, colors, tree_stats

from .shared import lemon, tree


def test_a_tree_counts_its_working_lemons_and_shows_its_fullest_context_and_latest_age():
    grown = tree(
        "t",
        dataclasses.replace(lemon("c:a"), working=True, context="41%", updated=1.0, age="2h ago"),
        dataclasses.replace(lemon("c:b"), context="88%", updated=3.0, age="4m ago"),
        dataclasses.replace(lemon("c:c"), updated=2.0, age="1h ago"),
    )
    assert tree_stats.line(grown) == "1/3 · 88% · 4m"


def test_a_tree_without_context_readings_leaves_them_out():
    assert tree_stats.line(tree("t", dataclasses.replace(lemon("c:a"), age="1d ago"))) == (
        "0/1 · 1d"
    )


def test_a_tagged_tree_marks_no_emoji_or_pin():
    marked = tree("t", dataclasses.replace(lemon("c:a"), emoji="🗺", pinned=True))
    (bare,) = tree_stats.tagged(marked).lemons
    assert (bare.emoji, bare.pinned) == ("", False)


def test_a_tags_context_reading_takes_the_inbox_color_and_keeps_the_tag_background():
    picture = canvas.blank(30, 1)
    canvas.text(picture, 0, 0, " 1/3 · 88% · 4m ", colors.TEXT, "#123456")
    tree_stats.color_context(picture, " 1/3 · 88% · 4m ", 0, 0)
    eights = [cell for cell in picture.rows[0] if cell.char in "88%"]
    assert {c.fg for c in eights} == {colors.reading_color("88%")}
    assert {c.bg for c in eights} == {"#123456"}
    assert picture.rows[0][1].fg == colors.TEXT
