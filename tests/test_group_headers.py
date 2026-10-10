"""A group header's fill and unread dot."""

from rich.console import Console

from lemonaid import groups
from lemonaid.inbox import sections
from lemonaid.inbox.tui import group_headers


def _header(band: str, unread: bool, collapsed: bool = True) -> sections.Header:
    group = groups.store.Group(1, "Watchers", 0, (), collapsed, "#c8a0f0")
    return sections.Header(group, 2, band, unread)


def test_an_unread_row_marks_a_collapsed_header_with_a_dot_rather_than_a_fill():
    text = group_headers.label(_header("unread", unread=True), width=30)

    assert "●" in text.plain
    assert group_headers.background(_header("unread", unread=True)) is None


def test_a_blocked_row_still_fills_a_collapsed_header():
    assert group_headers.background(_header("blocked", unread=True)) is not None


def test_a_header_with_nothing_unread_has_no_dot():
    assert "●" not in group_headers.label(_header("blocked", unread=False), width=30).plain


def _colour_at(text, offset: int) -> str | None:
    style = text.get_style_at_offset(Console(), offset)

    return style.color.get_truecolor().hex if style.color else None


def test_the_rule_and_count_of_an_open_header_take_the_groups_colour():
    text = group_headers.label(_header("read", unread=False, collapsed=False), width=30)

    assert _colour_at(text, text.plain.index("(")) == "#c8a0f0"
    assert _colour_at(text, 28) == "#c8a0f0"


def test_the_rule_takes_the_groups_colour_under_a_status_fill_but_the_count_keeps_the_fills():
    text = group_headers.label(_header("blocked", unread=False), width=30)

    assert _colour_at(text, 28) == "#c8a0f0"
    assert _colour_at(text, text.plain.index("(")) != "#c8a0f0"
