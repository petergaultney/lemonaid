"""Group header fills, status badges and cursor visibility."""

import pytest
from rich.console import Console

from lemonaid import groups
from lemonaid.inbox import sections
from lemonaid.inbox.tui.live import group_headers
from lemonaid.inbox.tui.rows.brief_cards import STATUS_STYLES


def _header(statuses=(), collapsed=True, color="#c8a0f0"):
    group = groups.store.Group(1, "Watchers", 0, ("one", "two"), collapsed, color=color)
    return sections.Header(group, 2, tuple((status, 1) for status in statuses))


@pytest.mark.parametrize("collapsed", [False, True])
@pytest.mark.parametrize("statuses", [(), ("blocked",), ("done",), ("alert", "merge", "done")])
def test_group_fill_covers_card_and_table_headers(collapsed, statuses):
    header = _header(statuses, collapsed=collapsed)
    assert group_headers.background(header).bgcolor.get_truecolor().hex == "#c8a0f0"
    for cells in (group_headers.cells(header, 35, 1, 0), group_headers.cells(header, 0, 5, 2)):
        for cell in cells:
            assert cell.style.bgcolor.get_truecolor().hex == "#c8a0f0"


def test_each_badge_has_colored_padding_after_a_group_colored_gap():
    header = _header(("alert", "blocked", "running", "merge", "approve", "review", "done"))
    text = group_headers.label(header, width=45)
    assert "  !1  ?1  N1  m1  ✓1  r1  d1 " in text.plain
    start = text.plain.index("!") - 1
    assert text.plain[start - 1] == " "
    assert text.get_style_at_offset(Console(), start - 1).bgcolor.get_truecolor().hex == "#c8a0f0"
    for offset, (status, _) in enumerate(header.status_counts):
        for cell in range(4):
            badge = text.get_style_at_offset(Console(), start + 4 * offset + cell)
            assert badge.color == STATUS_STYLES[status].color
            assert badge.bgcolor == STATUS_STYLES[status].bgcolor
            assert not badge.underline


@pytest.mark.parametrize(
    "color, foreground", [("#000000", "#ffffff"), ("#ffffff", "#000000"), ("#00cc00", "#000000")]
)
def test_header_text_contrasts_with_saved_group_colors(color, foreground):
    text = group_headers.label(_header(color=color), width=30)
    for offset in (0, text.plain.index("("), 28):
        assert text.get_style_at_offset(Console(), offset).color.get_truecolor().hex == foreground


def test_selected_long_header_keeps_tally_badges_and_cursor_in_a_narrow_sidebar():
    header = _header(("alert", "blocked", "done"))
    text = group_headers.label(header, width=28, selected=True, digit="2")
    assert text.cell_len == 28
    assert "(0/2)" in text.plain
    assert "  !1  ?1  d1 " in text.plain
    assert text.plain.endswith(" ◀ ")
    assert text.get_style_at_offset(Console(), 0).bgcolor.get_truecolor().hex == "#000000"


@pytest.mark.parametrize("width", [1, 2, 3, 5, 10])
def test_very_narrow_selected_header_stays_within_its_width(width):
    assert group_headers.label(_header(("alert",)), width, True).cell_len == width


@pytest.mark.parametrize("collapsed", [False, True])
@pytest.mark.parametrize("visible, tally", [(0, "0/2"), (1, "1/2"), (2, "2")])
def test_label_shows_visible_rows_out_of_members(collapsed, visible, tally):
    header = _header(collapsed=collapsed)
    header = sections.Header(header.group, 2, visible=visible)
    assert f"({tally})" in group_headers.label(header).plain


@pytest.mark.parametrize(
    "color, marker_background", [("#ffffff", "#000000"), ("#000000", "#ffffff")]
)
def test_selection_marker_contrasts_even_with_black_or_white_group_colors(color, marker_background):
    text = group_headers.label(_header(color=color), selected=True)
    assert text.get_style_at_offset(Console(), 0).bgcolor.get_truecolor().hex == marker_background


def test_column_header_shortens_the_name_before_its_status_counts():
    header = _header(("alert", "blocked", "running", "merge", "approve", "review", "done"))
    cells = group_headers.cells(header, 0, 5, 2, selected=True, name_width=40)
    assert cells[2].cell_len == 40
    assert "(0/2)" in cells[2].plain
    assert "  !1  ?1  N1  m1  ✓1  r1  d1 " in cells[2].plain
    assert "◀" not in cells[2].plain


def test_multi_digit_status_counts_stay_inside_the_colored_badge():
    header = _header(())
    header = sections.Header(header.group, 14, (("blocked", 12), ("merge", 2)))
    text = group_headers.label(header)
    assert text.plain.endswith("  ?12  m2 ")
    start = text.plain.index("?12")
    assert (
        text.get_style_at_offset(Console(), start + 2).bgcolor == STATUS_STYLES["blocked"].bgcolor
    )
