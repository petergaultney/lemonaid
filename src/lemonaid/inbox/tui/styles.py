"""The inbox's stylesheet and the theme variables it reads."""

from textual.color import Color, ColorParseError

from ...config import TuiConfig
from ...log import get_logger
from .utils import ATTENTION_COLOR

_log = get_logger("tui")

CSS = (
    f"$attention: {ATTENTION_COLOR};\n"
    + """
#content_switcher, #inbox_content {
    height: 1fr;
}

/* Shown by the app when a view, a search or the rows call for them. */
#history_filter, #fold_label, #other_sources_label, #other_sources_table,
#search_archive_label, #history_table, #snoozed_table, #usage_table {
    display: none;
}

#inbox_list, #main_table {
    height: 1fr;
}

#main_table.-custom-active-row > .datatable--cursor {
    background: $active-row-color;
}

App.-input-inactive #main_table > .datatable--cursor {
    background: $inactive-row-color;
}

/* HeaderIcon is only a second route to the command palette, which already
   has a keybinding in the footer. Hide its matching empty clock spacer too,
   so the title remains centred across the full pane. */
HeaderIcon, HeaderClockSpace {
    display: none;
}

/* Unlike tmux's half-border, these mark the pane that will receive keys.
   Keep them separate from the unread bar below the title. */
App.-input-active Screen {
    border-bottom: heavy $input-focus;
}

App.-input-active Header {
    background: $input-focus;
    color: $input-focus-text;
    text-style: bold;
}

/* The column layout's header row also carries the state of the list:
   whether anything in it wants you, and which list you are looking at.
   The attention colour is shared with the unread marker, so the bar and
   dot remain the same lemon yellow by construction. */
DataTable > .datatable--header {
    background: ansi_bright_blue;
}

DataTable {
    scrollbar-size-vertical: 1;
}

App.-unread DataTable > .datatable--header {
    background: $attention;
    color: ansi_black;
}

/* History is a record, not a queue. Same specificity as the unread rule
   above and deliberately after it: which list you are looking at outranks
   what is in the one you left. */
App.-history DataTable > .datatable--header {
    background: ansi_blue;
}

#fold_label {
    height: 1;
    color: $text-muted;
    padding: 0 1;
}

#other_sources_label {
    height: 1;
    background: $surface;
    color: $text-muted;
    padding: 0 1;
    text-style: italic;
}

#other_sources_table {
    height: auto;
    max-height: 8;
    color: $text-muted;
}

/* Only ever displayed while the Footer is hidden, so it takes the Footer's
   row rather than costing the list a second one. */
#status {
    height: 1;
    background: $surface;
    color: $text-muted;
    padding: 0 1;
}

#history_filter {
    height: 3;
    border: solid $accent;
}

#history_table {
    height: 1fr;
}

#search_archive_label {
    height: 1;
    background: $accent;
    color: $background;
    padding: 0 1;
    text-style: bold;
}

App.-search-archive #inbox_list, App.-search-archive #main_table {
    height: auto;
}

#snoozed_table, #usage_table {
    height: 1fr;
}
"""
)


def uses_custom_active_row(active_row_color: str, dark: bool) -> bool:
    if active_row_color:
        try:
            Color.parse(active_row_color)
        except ColorParseError:
            return dark

        return True

    return dark


def css_variables(
    variables: dict[str, str], tui: TuiConfig, custom_active_row: bool
) -> dict[str, str]:
    """`variables` plus the colours the stylesheet takes from config."""
    try:
        focus = Color.parse(tui.focus_color)
    except ColorParseError:
        _log.warning("tui.focus_color %r is not a colour", tui.focus_color)
        focus = Color.parse(TuiConfig.focus_color)
    active_row = "#1f4a85"
    if tui.active_row_color:
        try:
            active_row = Color.parse(tui.active_row_color).hex
        except ColorParseError:
            _log.warning("tui.active_row_color %r is not a colour", tui.active_row_color)
    cursor = Color.parse(
        active_row if custom_active_row else variables.get("block-cursor-background", active_row)
    )
    inactive_row = cursor.blend(Color.parse(variables.get("background", "#000000")), 0.7).hex
    if tui.inactive_row_color:
        try:
            inactive_row = Color.parse(tui.inactive_row_color).hex
        except ColorParseError:
            _log.warning("tui.inactive_row_color %r is not a colour", tui.inactive_row_color)
    return {
        **variables,
        "input-focus": focus.hex,
        "input-focus-text": focus.get_contrast_text(1.0).hex,
        "active-row-color": active_row,
        "inactive-row-color": inactive_row,
    }
