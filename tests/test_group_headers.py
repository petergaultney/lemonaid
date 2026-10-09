"""A group header's fill and unread dot."""

from lemonaid import groups
from lemonaid.inbox import sections
from lemonaid.inbox.tui import group_headers


def _header(band: str, unread: bool, collapsed: bool = True) -> sections.Header:
    group = groups.store.Group(1, "Watchers", 0, (), collapsed)
    return sections.Header(group, 2, band, unread)


def test_an_unread_row_marks_a_collapsed_header_with_a_dot_rather_than_a_fill():
    text = group_headers.label(_header("unread", unread=True), width=30)

    assert "●" in text.plain
    assert group_headers.background(_header("unread", unread=True)) is None


def test_a_blocked_row_still_fills_a_collapsed_header():
    assert group_headers.background(_header("blocked", unread=True)) is not None


def test_a_header_with_nothing_unread_has_no_dot():
    assert "●" not in group_headers.label(_header("blocked", unread=False), width=30).plain
