import dataclasses

from lemonaid.grove.draw import canvas, tag_fit, trees

from .shared import lemon, tree

NAMED = dataclasses.replace(tree("t"), label="project templates")
SHAPE = trees.shape(NAMED, "p", 1.0)


def _tag(ax: float, bounds: tuple[int, int] = (0, 200)) -> tag_fit.Tag:
    return tag_fit.Tag(NAMED, "p", SHAPE, ax, 10.0, 12, bounds)


def _rect(found: tag_fit.Fitted) -> tag_fit.Rect:
    return found.x, found.y, len(found.lines[0]), len(found.lines)


def test_a_tag_with_room_sits_under_its_crown_whole():
    (found,) = tag_fit.fit([_tag(50.0)], [])
    assert found.y == 14 and "project templates" in found.lines[0]
    assert found.x < 50 < found.x + len(found.lines[0])


def test_a_tag_never_covers_what_is_already_drawn():
    wall = (0, 14, 46, 2)
    (found,) = tag_fit.fit([_tag(50.0)], [wall])
    x, y, w, h = _rect(found)
    assert not (x < 46 + 1 and y < 16 and y + h > 14)
    assert x < 50 < x + w  # still over its trunk


def test_a_hemmed_in_tag_shortens_down_to_its_letter():
    walls = [(0, 14, 48, 3), (53, 14, 100, 3)]
    (found,) = tag_fit.fit([_tag(50.0)], walls)
    assert found.lines[0].split()[0] == "p"
    assert len(found.lines[0]) < SHAPE.width


def test_two_tags_side_by_side_do_not_touch():
    left, right = tag_fit.fit([_tag(50.0), _tag(60.0)], [])
    a, b = _rect(left), _rect(right)
    apart = a[0] + a[2] < b[0] or b[0] + b[2] < a[0] or a[1] + a[3] <= b[1] or b[1] + b[3] <= a[1]
    assert apart


def test_a_tag_stays_inside_its_block():
    (found,) = tag_fit.fit([_tag(50.0, bounds=(45, 70))], [])
    assert found.x >= 45 and found.x + len(found.lines[0]) <= 70


def test_a_short_tag_keeps_room_for_the_emoji_after_its_key():
    marked = dataclasses.replace(
        tree("t", dataclasses.replace(lemon("claude:t"), emoji="🌎")), label="spatial lemon jump"
    )
    short = trees.short_tag(marked, "s", 10)
    assert len(short) == 10 and short.startswith(" s     s")


def test_the_shortest_tag_keeps_its_letter_beside_the_emoji():
    marked = dataclasses.replace(
        tree("t", dataclasses.replace(lemon("claude:t"), emoji="🌎")), label="spatial lemon jump"
    )
    shape = trees.shape(marked, "s", 1.0)
    walls = [(0, 14, 48, 3), (53, 14, 100, 3)]
    (found,) = tag_fit.fit([tag_fit.Tag(marked, "s", shape, 50.0, 10.0, 12, (0, 200))], walls)
    picture = canvas.blank(120, 20)
    trees.draw_tag(picture, marked, found.lines, found.x, found.y, found.trunk, 0.0)
    drawn = canvas.plain_lines(picture)[found.y]
    assert "s" in drawn[found.x : found.x + 3] and "🌎" in drawn


def test_a_tag_slides_its_trunk_to_one_end_to_keep_its_whole_name():
    crown_on_the_left = (30, 13, 18, 3)
    (found,) = tag_fit.fit([_tag(50.0)], [crown_on_the_left])
    assert "project templates" in found.lines[0]
    assert found.x < 50 < found.x + len(found.lines[0])
