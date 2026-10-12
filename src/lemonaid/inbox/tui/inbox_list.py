"""The inbox's list of live sessions: the main table, its fold line, and the other-terminals table.

It owns what persists between refreshes - the fold, the arranger, the group
headers drawn, where the cursor should follow - and redraws from the database
when the app asks it to.
"""

import contextlib
import time
from collections import abc

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Static

from ...config import PlaceRoot
from ...log import get_logger
from .. import db, presence, sections, unarchive, view
from . import (
    cursor_target,
    focus,
    group_headers,
    inbox_arrange,
    inbox_draw,
    inbox_frame,
    layout,
    pr_numbers,
    row_keys,
    row_parts,
    table_rows,
)
from .table import ClickToActTable
from .utils import GUTTER_WIDTH, update_static

_log = get_logger("tui")

_MIN_MAIN_ROWS = 5  # the other-terminals table hides rather than squeeze the main one below this


class InboxList(Vertical):
    def __init__(
        self,
        lists: row_parts.Lists,
        redraw: abc.Callable[[], None],
        *,
        id: str,
    ) -> None:
        """`redraw` refreshes the whole inbox, this list included, after an edit or once
        something fetched in the background has arrived.
        """
        super().__init__(id=id)
        self.config = lists.config
        self._parts = lists.parts
        self._brief_cache = lists.brief_cache
        self.undo_stack = lists.undo_stack
        self.redraw = redraw
        self.presence = presence.Probe(presence.DEAF_AFTER_SECONDS)
        self.pr_numbers = pr_numbers.Cache()
        self.arrangement = inbox_arrange.Arrangement(lists.config)
        self.fold_open = False
        self.fold_name = ""  # the arranger's name for the folded group
        self._unfolded_ids: frozenset[str] = (
            frozenset()
        )  # rows the last refresh kept out of the fold
        self.drawn: list[db.Notification | None] = []  # the main table's rows; None for a header
        self.group_bands: dict[int, str] = {}  # each drawn group's band, by group id
        self.headers: dict[str, sections.Header] = {}  # the drawn headers, by row key
        self._marked_header = ""  # the header drawn with the cursor's marker
        self._followed_focus: frozenset[str] = frozenset()  # the lemons the cursor last went to
        # The row a group was collapsed from, drawn until the cursor leaves it.
        self.kept: frozenset[str] = frozenset()
        self._restore_checked: frozenset[str] = frozenset()

    def compose(self) -> ComposeResult:
        yield ClickToActTable(id="main_table")
        yield Static("", id="fold_label")
        yield Static("", id="other_sources_label")
        yield DataTable(id="other_sources_table", show_header=False)

    def on_unmount(self) -> None:
        self.arrangement.close()

    @property
    def main(self) -> DataTable:
        return self.query_one("#main_table", DataTable)

    @property
    def other(self) -> DataTable:
        return self.query_one("#other_sources_table", DataTable)

    def _refresh_pr_numbers(self) -> None:
        for root in self.pr_numbers.due(self.config.places.roots, time.monotonic()):

            def load(root: PlaceRoot = root) -> None:
                numbers = pr_numbers.refresh(root)
                self.app.call_from_thread(self.pr_numbers.store, root, numbers, time.monotonic())
                self.app.call_from_thread(self.redraw)

            self.run_worker(load, thread=True, group="pr-numbers")

    def _follow_focus(
        self,
        entries: list[sections.Header | sections.Row],
        frame: inbox_frame.Frame,
        current_key: str | None,
    ) -> int | None:
        """The row to move to when the focused lemon has changed, by whatever route,
        unless the cursor is already on one of its rows.
        """
        if frame.focused_channels == self._followed_focus:
            return None

        self._followed_focus = frame.focused_channels
        if any(
            str(n.id) == current_key and n.channel in frame.focused_channels
            for n in frame.active.rows
        ):
            return None

        return focus.first_row(entries, frame.focused_channels)

    def refresh_list(
        self,
        *,
        focused: frozenset[str],
        env_filter: str | None,
        search_text: str | None,
        detached: abc.Set[str],
        cards: bool,
        width: int,
        height: int,
        card_width: int,
        card_shape: abc.Callable[[int], tuple[int, int]],
        stay_on_unread: bool = False,
    ) -> inbox_draw.Drawn:
        """Redraw both tables from the database.

        `search_text` is None outside a search, `card_shape` sizes cards for a
        given number of extra brief lines, and `width` and `height` are the pane's.
        """
        self._refresh_pr_numbers()
        main = self.main
        other = self.other
        fold_label = self.query_one("#fold_label", Static)

        # Remember current selection (both key and index) for both tables
        current_key = row_keys.notification_at_cursor(main)
        current_row = row_keys.at_cursor(main)  # a header's, or a lemon's under its group
        self.kept = self.kept if current_row in self.kept else frozenset()
        current_index = main.cursor_coordinate.row
        other_index = other.cursor_coordinate.row if other.row_count > 0 else 0
        focused_on_other = self.app.focused is other
        other_key = row_keys.notification_at_cursor(other) if focused_on_other else None

        with db.connect() as conn:
            if focused != self._restore_checked:
                self._restore_checked = focused  # asked once per change of focus: it can cost a ps
                unarchive.restore_focused(conn, focused)
            frame = inbox_frame.load(
                conn,
                self.config,
                self._brief_cache,
                self.presence,
                self.pr_numbers,
                env_filter=env_filter,
                focused=focused,
                search_text=search_text,
                current_key=current_key,
                other_key=other_key,
                unfolded_ids=self._unfolded_ids,
                now=time.time(),
            )

        active = frame.active
        card_briefs = active.cards
        shown, folded, self.fold_name = self.arrangement.arranged(
            active, frame.shown, frame.folded, frame.pinned, frame.emojis, cards, width
        )
        self._unfolded_ids = frozenset(str(n.id) for n in shown)
        all_folded = folded  # grouped ones too, which hide in place rather than in the fold
        other_notifications = frame.other
        entries: list[sections.Header | sections.Row]
        if frame.matching_ids is not None:
            entries = [
                sections.Row(str(n.id), n) for n in [*shown, *folded] if n.id in frame.matching_ids
            ]
            other_notifications = [n for n in other_notifications if n.id in frame.matching_ids]
        else:
            entries, folded = sections.layout(
                shown,
                folded,
                frame.pinned,
                active.memberships,
                frame.groups,
                view.statuses(card_briefs, active.rows),
                self.kept,
                self.fold_open,
                active.deaf,
            )
            if self.fold_open:
                entries = [*entries, *(sections.Row(str(n.id), n) for n in folded)]
        drawn = [e for e in entries if isinstance(e, sections.Row)]
        numbers_by_key = {e.key: i for i, e in enumerate(drawn)}  # jump digits skip headers
        briefs = (
            {
                e.key: card_briefs[e.notification.channel]
                for e in drawn
                if e.notification.channel in card_briefs
            }
            if self.config.tui.brief_status
            else {}
        )
        age_inline = "age" in self.config.tui.card_fields
        extra_lines = max(
            (card.extra_lines(age_inline) for card in briefs.values() if card and card_width),
            default=0,
        )
        now = time.time()

        self.drawn = [e.notification if isinstance(e, sections.Row) else None for e in entries]
        self.group_bands = {
            e.group.group_id: e.band for e in entries if isinstance(e, sections.Header)
        }
        areas = {channel: card.area for channel, card in card_briefs.items() if card.area}
        unread_count = len({e.notification.id for e in drawn if e.notification.is_unread})
        self.headers = {e.key: e for e in entries if isinstance(e, sections.Header)}
        self._marked_header = current_row if current_row in self.headers else ""
        headers = {
            e.key: (
                group_headers.cells(
                    e, card_width, len(main.columns), layout.NAME_CELL, e.key == self._marked_header
                ),
                group_headers.background(e),
            )
            for e in entries
            if isinstance(e, sections.Header)
        }
        rebuilt = table_rows.sync_rows(
            main,
            [
                (e.key, headers[e.key][0])
                if isinstance(e, sections.Header)
                else (
                    e.key,
                    inbox_draw.active_row(
                        e.notification,
                        numbers_by_key[e.key],
                        frame,
                        detached,
                        areas.get(e.notification.channel, ""),
                        self._parts,
                        self.config,
                    ),
                )
                for e in entries
            ],
            card_width,
            card_shape(extra_lines),
            GUTTER_WIDTH,
            self.config.tui.card_unread_style,
            {e.key: frame.emojis.get(e.notification.channel, "") for e in drawn},
            briefs,
            now,
            {
                e.key: self._parts.context_parts(
                    e.notification,
                    e.notification.is_unread,
                    areas.get(e.notification.channel, ""),
                    briefs.get(e.key),
                    now,
                )
                for e in drawn
            },
            age_inline,
            self.config.tui.project_name_colors,
            headers,
            {
                e.key: self.headers[f"group:{group}"].group.colour
                for e in drawn
                if (group := sections.row_group_id(e.key)) is not None
                and f"group:{group}" in self.headers
            },
        )

        fold_label.display = bool(all_folded) and search_text is None
        update_static(
            fold_label,
            inbox_draw.fold_label(
                self.config,
                self.fold_name,
                self.fold_open,
                len(all_folded),
                len(
                    {
                        name
                        for n in [*shown, *all_folded]
                        for name in active.memberships.get(n.channel, ())
                    }
                )
                - len(self.headers),
            ),
        )

        # The non-switchable table hides if the terminal is too short: the main table gets priority.
        chrome = 3 + bool(folded)  # header, other_label, the status/footer row, the fold line
        show_other = bool(other_notifications) and (
            height - chrome - min(len(other_notifications), 8) >= _MIN_MAIN_ROWS
        )
        if show_other:
            inbox_draw.other_table(
                self.query_one("#other_sources_label", Static),
                other,
                other_notifications,
                frame,
                areas,
                self._parts,
                self.config,
                card_width,
                card_shape(0),
            )
        else:
            if other.row_count:
                other.clear()
            self.query_one("#other_sources_label", Static).display = False
            other.display = False
            if focused_on_other:
                main.focus()

        if other.row_count > 0:
            other_target = None
            if other_key:
                with contextlib.suppress(Exception):
                    other_target = other.get_row_index(other_key)
            other.move_cursor(
                row=other_target
                if other_target is not None
                else min(other_index, other.row_count - 1)
            )

        # An in-place update leaves the cursor where it was, so only a rebuild (or an
        # explicit jump) moves it; moving it every tick made the list flash to the top.
        follow = self._follow_focus(entries, frame, current_key)
        if main.row_count > 0 and follow is not None:
            main.move_cursor(row=follow)
        elif main.row_count > 0 and stay_on_unread:
            main.move_cursor(
                row=cursor_target.after_unread_action(
                    [i for i, n in enumerate(self.drawn) if n and n.is_unread], current_index
                )
            )
        elif main.row_count > 0 and rebuilt:
            main.move_cursor(
                row=cursor_target.after_rebuild(main, current_row, current_key, current_index)
            )
        return inbox_draw.Drawn(
            unread_count,
            len(active.rows) - unread_count,
            len(drawn) + len(other_notifications),
            bool(other_notifications),
            show_other,
        )

    def mark_header(self, key: str, card_width: int) -> None:
        """Move the cursor's marker to the header at *key*, or off every header."""
        wanted = key if key in self.headers else ""
        if wanted == self._marked_header:
            return

        table = self.main
        for changed in (self._marked_header, wanted):
            if not changed:
                continue

            cells = group_headers.cells(
                self.headers[changed],
                card_width,
                len(table.columns),
                layout.NAME_CELL,
                changed == wanted,
            )
            with contextlib.suppress(Exception):  # the row may be gone before a refresh
                row = table.get_row_index(changed)
                for column, value in enumerate(cells):
                    table.update_cell_at((row, column), value, update_width=False)
        self._marked_header = wanted

    def select_key(self, key: str) -> None:
        with contextlib.suppress(Exception):
            self.main.move_cursor(row=self.main.get_row_index(key))

    def jump_unread(self) -> bool:
        """Switch to the earliest unread session; False when there is none.

        Pins and status bands spread unread rows through the list, so the
        earliest is found by age rather than by position.
        """
        unread = [(n.created_at, row) for row, n in enumerate(self.drawn) if n and n.is_unread]
        if not unread:
            return False

        self.main.move_cursor(row=min(unread)[1])
        self.main.action_select_cursor()
        return True

    def move_to_lemon(self, nth: int) -> bool:
        """Put the cursor on the *nth* lemon drawn; headers are unnumbered."""
        lemons = [row for row, n in enumerate(self.drawn) if n is not None]
        if not 0 <= nth < len(lemons):
            return False

        self.main.move_cursor(row=lemons[nth])
        return True
