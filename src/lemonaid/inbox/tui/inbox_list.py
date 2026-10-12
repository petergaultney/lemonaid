"""The inbox's list of live sessions: the main table, its fold line, and the other-terminals table.

It owns what persists between refreshes - the fold, the arranger, the group
headers drawn, where the cursor should follow - and redraws from the database
when the app asks it to.
"""

import contextlib
import dataclasses
import time
from collections import abc

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Static

from ... import groups
from ... import resume as resume_mod
from ...config import Config, PlaceRoot
from ...log import get_logger
from .. import db, presence, sections, unarchive, undo, view
from ..arrange import answer, child
from . import (
    brief_cards,
    cursor_target,
    focus,
    group_headers,
    inbox_frame,
    inbox_rows,
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


@dataclasses.dataclass(frozen=True)
class Drawn:
    """Counts from one refresh, for the status line."""

    unread: int
    read: int
    matches: int  # rows in both tables; only meaningful while searching
    other: bool  # whether any other-terminal rows exist
    other_shown: bool


def can_resume_detached(notification: db.Notification, config: Config) -> bool:
    return notification.switch_source in {"tmux", "cmux"} and bool(
        resume_mod.build_resume_command(config, notification.channel, notification.metadata)
    )


def detached_marker(notification: db.Notification, detached: abc.Set[str], config: Config) -> Text:
    if notification.channel not in detached:
        return Text()

    marker = Text(" · detached", style="dim")
    if not can_resume_detached(notification, config):
        marker.append(" · resume unavailable", style="dim red")

    return marker


class InboxList(Vertical):
    def __init__(
        self,
        config: Config,
        parts: row_parts.RowParts,
        brief_cache: brief_cards.BriefCache,
        undo_stack: undo.Stack,
        redraw: abc.Callable[[], None],
        *,
        id: str,
    ) -> None:
        """`redraw` refreshes the whole inbox, this list included, after an edit or once
        something fetched in the background has arrived.
        """
        super().__init__(id=id)
        self.config = config
        self._parts = parts
        self._brief_cache = brief_cache
        self.undo_stack = undo_stack
        self.redraw = redraw
        self.presence = presence.Probe(presence.DEAF_AFTER_SECONDS)
        self.pr_numbers = pr_numbers.Cache()
        self.arranger = (
            child.Arranger(child.parse_command(config.inbox.arrange))
            if config.inbox.arrange
            else None
        )
        self.arrange_error = ""
        self._arrange_logged: set[str] = set()
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
        if self.arranger is not None:
            self.arranger.close()

    @property
    def main(self) -> DataTable:
        return self.query_one("#main_table", DataTable)

    @property
    def other(self) -> DataTable:
        return self.query_one("#other_sources_table", DataTable)

    def _arranged(
        self,
        active: view.Active,
        shown: list[db.Notification],
        folded: list[db.Notification],
        pinned: frozenset[str],
        emojis: abc.Mapping[str, str],
        cards: bool,
        width: int,
    ) -> tuple[list[db.Notification], list[db.Notification], str]:
        """*shown* and *folded* as the arranger has them, and its fold label.

        While it has no usable answer they come back as they are, and
        `arrange_error` says why for the status line.
        """
        if self.arranger is None:
            return shown, folded, ""

        now = time.time()
        reply = self.arranger.answer(
            view.snapshot(
                active, shown, folded, pinned, emojis, "sidebar" if cards else "table", width, now
            ),
            now,
        )
        self.arrange_error = self.arranger.error
        if reply is None:
            return shown, folded, ""

        try:
            arranged = answer.apply(
                reply, shown, folded, self.config.inbox.arrange_may_fold_unread, active.deaf
            )
        except answer.AnswerError as e:
            if str(e) not in self._arrange_logged:
                _log.warning("arrange: %s", e)
                self._arrange_logged.add(str(e))
            self.arrange_error = str(e)
            return shown, folded, ""

        if len(self._arrange_logged) > 1000:
            self._arrange_logged.clear()  # problems name row ids, which keep changing
        for problem in set(arranged.problems) - self._arrange_logged:
            _log.info("arrange: %s", problem)
        self._arrange_logged.update(arranged.problems)
        return arranged.shown, arranged.folded, arranged.fold_label

    def _refresh_pr_numbers(self) -> None:
        for root in self.pr_numbers.due(self.config.places.roots, time.monotonic()):

            def load(root: PlaceRoot = root) -> None:
                numbers = pr_numbers.refresh(root)
                self.app.call_from_thread(self.pr_numbers.store, root, numbers, time.monotonic())
                self.app.call_from_thread(self.redraw)

            self.run_worker(load, thread=True, group="pr-numbers")

    def _fold_label(self, count: int, hidden_groups: int = 0) -> str:
        """The fold's one line: which statuses, how many, any groups it hides, and its key.

        *count* includes folded rows in groups, which hide in place under
        their headers, and *hidden_groups* the groups with every row folded.
        """
        key = self.config.tui.keybindings.fold[:1]
        group = (
            f"{self.fold_name or ', '.join(self.config.tui.fold_statuses) or 'folded'} ({count})"
        )
        if self.fold_open:
            return f"▴ {group} above" + (f" · {key} to fold" if key else "")

        hidden = f" · {hidden_groups} group{'s' if hidden_groups != 1 else ''} hidden"
        return (
            f"▸ {group}"
            + (hidden if hidden_groups > 0 else "")
            + (f" · {key} to show" if key else "")
        )

    def _active_row(
        self,
        n: db.Notification,
        row_index: int,
        frame: inbox_frame.Frame,
        detached: abc.Set[str],
        area: str,
    ) -> list[Text]:
        return inbox_rows.active_row(
            n,
            row_index,
            n.channel in frame.focused_channels,
            n.channel in frame.pinned,
            frame.emojis,
            self._parts.backend_value(n, n.is_unread),
            self._parts.where_cell(n, n.is_unread, area),
            detached_marker(n, detached, self.config),
            self.config.tui,
            frame.wordybins.get(n.channel, ""),
            frame.numbers.get(n.channel),
        )[1]

    def _draw_other(
        self,
        rows: list[db.Notification],
        frame: inbox_frame.Frame,
        areas: abc.Mapping[str, str],
        card_width: int,
        card_shape: tuple[int, int],
    ) -> None:
        label = self.query_one("#other_sources_label", Static)
        label.update("── non-switchable ──")
        label.display = True
        self.other.display = True
        table_rows.sync_rows(
            self.other,
            [
                inbox_rows.other_row(
                    n,
                    frame.emojis,
                    self._parts.backend_value(n, False),
                    self._parts.where_cell(n, False, areas.get(n.channel, "")),
                    self.config.tui,
                    frame.wordybins.get(n.channel, ""),
                    frame.numbers.get(n.channel),
                )
                for n in rows
            ],
            card_width,
            card_shape,
            contexts_by_row={
                str(n.id): self._parts.context_parts(n, False, areas.get(n.channel, ""))
                for n in rows
            },
        )

    def _restore_main_cursor(
        self,
        entries: list[sections.Header | sections.Row],
        frame: inbox_frame.Frame,
        current_row: str | None,
        current_key: str | None,
        current_index: int,
        rebuilt: bool,
        stay_on_unread: bool,
    ) -> None:
        """An in-place update leaves the cursor where it was, so only a rebuild (or an
        explicit jump) moves it; moving it every tick made the list flash to the top.

        When the focused lemon changes, by whatever route, the cursor goes to its
        row, unless the cursor is already on one of its rows.
        """
        main = self.main
        follow = None
        if frame.focused_channels != self._followed_focus:
            self._followed_focus = frame.focused_channels
            if not any(
                str(n.id) == current_key and n.channel in frame.focused_channels
                for n in frame.active.rows
            ):
                follow = focus.first_row(entries, frame.focused_channels)
        if main.row_count > 0 and follow is not None:
            main.move_cursor(row=follow)
        elif main.row_count > 0 and (rebuilt or stay_on_unread):
            target_index = None
            unread_rows = [i for i, n in enumerate(self.drawn) if n and n.is_unread]
            if stay_on_unread:
                target_index = cursor_target.after_unread_action(unread_rows, current_index)
            else:
                # The same row, else the same lemon wherever it went, else the same place
                for key in (current_row, current_key):
                    if key and target_index is None:
                        with contextlib.suppress(Exception):
                            target_index = main.get_row_index(key)
                if target_index is None and current_key:
                    # Into or out of a group, or between groups, its key changed.
                    target_index = next(
                        (
                            i
                            for i, key in enumerate(main.rows)
                            if str(sections.notification_id(str(key.value))) == current_key
                        ),
                        None,
                    )
                if target_index is None:
                    target_index = min(current_index, main.row_count - 1)
            main.move_cursor(row=target_index)

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
    ) -> Drawn:
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
        shown, folded, self.fold_name = self._arranged(
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
                    self._active_row(
                        e.notification,
                        numbers_by_key[e.key],
                        frame,
                        detached,
                        areas.get(e.notification.channel, ""),
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
            self._fold_label(
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
            self._draw_other(other_notifications, frame, areas, card_width, card_shape(0))
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

        self._restore_main_cursor(
            entries, frame, current_row, current_key, current_index, rebuilt, stay_on_unread
        )
        return Drawn(
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

    def selected_group(self) -> "groups.store.Group | None":
        """The group whose header is under the cursor."""
        raw = row_keys.at_cursor(self.main)
        found = sections.group_id(raw) if raw else None
        if found is None:
            return None

        with db.connect() as conn:
            return next((g for g in groups.store.all_groups(conn) if g.group_id == found), None)

    def toggle_group(self, group_id: int, from_row: str = "") -> None:
        """Collapse an open group to its header, or open a collapsed one.

        Collapsing from one of its lemons keeps that lemon drawn, under the
        cursor, until the cursor moves off it.
        """
        with db.connect() as conn:
            group = next((g for g in groups.store.all_groups(conn) if g.group_id == group_id), None)
            if group is None:
                return

            groups.arrangement.set_collapsed(conn, group, not group.collapsed)

        self.kept = frozenset({from_row} if from_row and not group.collapsed else ())
        self.redraw()
        self.select_key(from_row or f"group:{group_id}")

    def toggle_group_at_cursor(self) -> None:
        """Open or collapse the group whose header or lemon is under the cursor."""
        raw = row_keys.at_cursor(self.main) or ""
        if (found := sections.group_id(raw)) is not None:
            self.toggle_group(found)
            return

        if (found := sections.row_group_id(raw)) is not None:
            self.toggle_group(found, from_row=raw)

    def move_group(self, group: "groups.store.Group", offset: int) -> str:
        """Trade places with the group header *offset* away on screen; a refusal's reason.

        Groups sort by their most pressing row first, so only the order among
        groups drawn next to each other is the user's to change.
        """
        table = self.main
        on_screen = [
            found
            for row in range(table.row_count)
            if (key := row_keys.at_row(table, row)) is not None
            and (found := sections.group_id(str(key.value))) is not None
        ]
        neighbour = on_screen.index(group.group_id) + offset
        if not 0 <= neighbour < len(on_screen):
            return ""

        if self.group_bands.get(on_screen[neighbour]) != self.group_bands.get(group.group_id):
            return "Groups sort by their most pressing lemon; this one can't pass that group"

        with db.connect() as conn:
            other = next(
                (g for g in groups.store.all_groups(conn) if g.group_id == on_screen[neighbour]),
                None,
            )
            if other is None:
                return ""

            groups.arrangement.swap(conn, group, other)

        self.redraw()
        self.select_key(f"group:{group.group_id}")
        return ""

    def earliest_unread_row(self) -> int | None:
        """Pins and status bands spread unread rows through the list, so the earliest
        is found by age rather than by position.
        """
        unread = [(n.created_at, row) for row, n in enumerate(self.drawn) if n and n.is_unread]
        return min(unread)[1] if unread else None

    def lemon_row(self, nth: int) -> int | None:
        """The row of the *nth* lemon drawn; headers are unnumbered."""
        lemons = [row for row, n in enumerate(self.drawn) if n is not None]
        return lemons[nth] if 0 <= nth < len(lemons) else None
