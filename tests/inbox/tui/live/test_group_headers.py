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
    for cells in (
        group_headers.cells(header, 35, [35], 0),
        group_headers.cells(header, 0, [5, 5, 20, 10, 40], 2),
    ):
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


def test_without_room_after_the_name_badges_follow_the_tally():
    header = _header(("alert", "blocked", "running", "merge", "approve", "review", "done"))
    cells = group_headers.cells(header, 0, [5, 5, 40, 3, 0], 2, selected=True)
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


def _slots(cells) -> str:
    return "".join(cell.plain for cell in cells[3:])


def test_each_status_keeps_its_slot_at_the_right_of_every_bar():
    widths = [5, 5, 30, 10, 30]
    merge_and_done = group_headers.cells(_header(("merge", "done")), 0, widths, 2)
    blocked_and_done = group_headers.cells(_header(("blocked", "done")), 0, widths, 2)

    assert _slots(merge_and_done).endswith(" m1          d1 ")
    assert _slots(blocked_and_done).endswith(" ?1                  d1 ")
    assert len(_slots(merge_and_done)) == len(_slots(blocked_and_done)) == 40
    assert "m1" not in merge_and_done[2].plain


def test_a_slot_never_straddles_two_cells():
    widths = [5, 5, 30, 10, 26]  # the last cell holds six slots; the seventh moves left
    text = _slots(group_headers.cells(_header(("alert", "done")), 0, widths, 2))

    assert text[:10].endswith(" !1 ")
    assert text.endswith(" d1 ")


def test_without_room_for_every_slot_badges_pack_at_the_right():
    cells = group_headers.cells(_header(("blocked", "done")), 0, [5, 5, 14, 10, 12], 2)

    assert _slots(cells).endswith(" ?1  d1 ")
    assert len(cells[4].plain) == 12


def test_a_wide_card_gives_badges_slots_and_a_narrow_one_packs_them():
    wide = group_headers.label(_header(("blocked", "done")), width=60)
    narrow = group_headers.label(_header(("blocked", "done")), width=30)

    assert wide.plain.endswith(" ?1                  d1    ")  # the marker's cells stay clear
    assert narrow.plain.endswith(" ?1  d1    ")


def test_slots_reach_into_the_name_cell_alike_for_every_header():
    widths = [5, 5, 47, 0, 14, 0, 0]  # a medium inbox: only Project follows the name
    bars = [
        "".join(cell.plain for cell in group_headers.cells(_header(statuses), 0, widths, 2))
        for statuses in (("blocked", "merge", "review", "done"), ("running", "review"), ("done",))
    ]

    assert len({bar.index("r1") for bar in bars if "r1" in bar}) == 1
    assert len({bar.index("d1") for bar in bars if "d1" in bar}) == 1
    assert bars[0].index("?1") + 8 == bars[1].index("N1") + 4 == bars[0].index("m1")


def test_a_two_digit_count_widens_every_headers_slots_alike():
    ten = sections.Header(_header().group, 10, (("merge", 1), ("done", 10)))
    one = _header(("merge", "done"))
    widths = [5, 5, 30, 10, 40]
    slot = group_headers.slot_width([ten, one])
    bars = [
        "".join(c.plain for c in group_headers.cells(h, 0, widths, 2, slot=slot))
        for h in (ten, one)
    ]

    assert slot == 5
    assert bars[0].index("m1") == bars[1].index("m1")
    assert bars[0].endswith(" d10 ") and bars[1].endswith(" d1 ")  # one right edge


@pytest.mark.parametrize("width", [50, 51, 60])
def test_selecting_a_card_leaves_its_badges_where_they_were(width):
    header = _header(("merge", "done"))
    plain = group_headers.label(header, width).plain
    selected = group_headers.label(header, width, selected=True).plain

    assert plain.index("m1") == selected.index("m1")
    assert plain.index("d1") == selected.index("d1")


@pytest.mark.parametrize(
    "card_width, widths, name_cell", [(60, [60], 0), (0, [10, 1, 6, 24, 12, 16, 40, 7], 3)]
)
def test_slot_starts_are_where_the_bars_draw_their_badges(card_width, widths, name_cell):
    header = _header(("blocked", "done"))
    padding = 0 if card_width else 1
    row = "".join(
        " " * padding + cell.plain.ljust(width) + " " * padding
        for cell, width in zip(
            group_headers.cells(header, card_width, widths, name_cell), widths, strict=True
        )
    )

    starts = group_headers.slot_starts(card_width, widths, name_cell, padding)

    assert row.index("?1") == starts["blocked"] + 1
    assert row.index("d1") == starts["done"] + 1


def test_slot_starts_are_empty_when_the_bars_pack_their_badges():
    assert group_headers.slot_starts(30, [30], 0, 0) == {}
