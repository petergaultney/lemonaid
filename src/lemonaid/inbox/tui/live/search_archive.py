"""The archive's matches under a search's inbox matches, when there is room for them."""

from textual.widgets import DataTable, Static

from ..tables import table_layout
from ..utils import update_static


def show(
    label: Static,
    archive: DataTable,
    main: DataTable,
    other: DataTable | None,
    count: int,
    room: int,
    other_squeezed: bool,
) -> bool:
    """Label and show *archive* below the inbox tables if it fits in *room* rows.

    `other` is the other-terminals table when it is shown; `other_squeezed`
    means it has rows but no room, and then the archive stays hidden too.
    """
    update_static(label, f"━ ARCHIVE · {count} MATCH{'ES' if count != 1 else ''} ━")
    inbox_height = int(main.show_header) + sum(row.height for row in main.rows.values())
    if other is not None:
        inbox_height += 1 + min(8, sum(row.height for row in other.rows.values()))

    shown = bool(count) and not other_squeezed
    if shown:
        shown = table_layout.archive_fits(
            room,
            inbox_height,
            int(archive.show_header),
            next(iter(archive.rows.values())).height,
        )
    archive.display = shown
    label.display = shown
    return shown
