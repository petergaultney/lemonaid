"""The usage pace figure in the header, and the usage view's table."""

import time

from rich.text import Text
from textual.content import Content
from textual.widgets import DataTable, Header
from textual.widgets._header import HeaderTitle

from ...log import get_logger
from ...usage import color, overall, samples, settings, table

_log = get_logger("inbox.usage_view")

_COLUMNS = (
    ("Window", 28),
    ("Pace", 7),
    ("Used", 7),
    ("Elapsed", 8),
    ("Resets", 30),
)


def read_samples() -> dict[str, samples.Sample]:
    """Empty, with a log line, when the usage files can't be read."""
    try:
        return samples.current_samples()
    except (OSError, ValueError, KeyError, TypeError):
        _log.warning("could not read usage", exc_info=True)

        return {}


def _rgb(ratio: float | None, config: settings.UsageConfig) -> str:
    if ratio is None:
        return "dim"

    r, g, b = color.pace_rgb(ratio, config.pace_color_ratios)

    return f"rgb({r},{g},{b})"


class UsageHeader(Header):
    """A Header with the overall pace, colored like `lemonaid usage`, after the title."""

    _usage: Content = Content("")

    def format_title(self) -> Content:
        return Content.assemble(super().format_title(), self._usage)

    def show_usage(self, figure: overall.Overall | None, config: settings.UsageConfig) -> None:
        self._usage = (
            Content("")
            if figure is None
            else Content.assemble("  ", (f"usage {figure.pace:.2f}x", _rgb(figure.pace, config)))
        )
        if self.is_mounted:
            self.query_one(HeaderTitle).update(self.format_title())


def setup_table(usage_table: DataTable) -> None:
    for label, width in _COLUMNS:
        usage_table.add_column(label, width=width)


def fill_table(usage_table: DataTable, rows: list[table.Row], config: settings.UsageConfig) -> None:
    usage_table.clear()
    for r in rows:
        used = color.used_rgb(r.used_percent)
        usage_table.add_row(
            r.window,
            Text("-" if r.pace is None else f"{r.pace:.2f}x", style=_rgb(r.pace, config)),
            Text(f"{r.used_percent:g}%", style=f"rgb({used[0]},{used[1]},{used[2]})"),
            f"{r.elapsed_percent:.0f}%",
            r.resets,
        )


def show(
    header: UsageHeader,
    usage_table: DataTable | None,
    current: dict[str, samples.Sample],
    config: settings.UsageConfig,
) -> None:
    now = time.time()
    header.show_usage(
        overall.overall(current, now, config) if config.overall_pace else None, config
    )
    if usage_table is not None:
        fill_table(usage_table, table.rows(current, now, config), config)
