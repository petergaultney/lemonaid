from rich.text import Text

from lemonaid.inbox.tui.rows import parent_markers


def test_lead_marker_sits_before_the_child_count_and_emoji():
    assert parent_markers.indicators(3, "E", Text(), lead=True).plain == "\u265b \u21933 E"


def test_no_marker_without_lead():
    assert "\u265b" not in parent_markers.indicators(3, "E", Text()).plain
