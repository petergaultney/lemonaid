"""Anchor a Markdown view refresh to the rendered text in its viewport."""

import contextlib
import dataclasses
import difflib
import typing as ty
from collections import Counter, abc

from textual.containers import VerticalScroll
from textual.geometry import Region
from textual.widget import Widget
from textual.widgets import Markdown, Static


class StableScroll(VerticalScroll):
    scroll_request = 0

    def scroll_to(self, x: float | None = None, y: float | None = None, **kwargs: ty.Any) -> None:
        self.scroll_request += 1
        super().scroll_to(x, y, **kwargs)

    def _scroll_to(self, x: float | None = None, y: float | None = None, **kwargs: ty.Any) -> bool:
        self.scroll_request += 1
        return super()._scroll_to(x, y, **kwargs)


@dataclasses.dataclass(frozen=True)
class _Position:
    lines: tuple[tuple[str, int], ...]
    x: float
    y: float


def _capture(view: VerticalScroll) -> _Position:
    lines = []
    for widget in view.query(Static):
        if widget.children or widget.styles.dock != "none" or not widget.region.height:
            continue
        top = widget.virtual_region.y + widget.styles.gutter.top
        parent = widget.parent
        while isinstance(parent, Widget) and parent is not view:
            top += parent.virtual_region.y + parent.styles.gutter.top
            parent = parent.parent
        for i, strip in enumerate(
            widget.render_lines(Region(0, 0, widget.size.width, widget.size.height))
        ):
            if strip.text.strip():
                lines.append((strip.text.strip(), top + i))
    return _Position(tuple(lines), view.scroll_x, view.scroll_y)


def _restore(view: VerticalScroll, before: _Position) -> None:
    after = _capture(view)
    matches = difflib.SequenceMatcher(
        None, [text for text, _ in before.lines], [text for text, _ in after.lines], autojunk=False
    )
    anchors = [
        (before.lines[old + i][1], after.lines[new + i][1])
        for old, new, size in matches.get_matching_blocks()
        for i in range(size)
    ]
    counts = Counter(text for text, _ in before.lines)
    destinations: dict[str, list[int]] = {}
    for text, y in after.lines:
        destinations.setdefault(text, []).append(y)
    anchors.extend(
        (y, destinations[text][0])
        for text, y in before.lines
        if counts[text] == 1 and len(destinations.get(text, ())) == 1
    )
    visible = [(old, new) for old, new in anchors if old >= before.y]
    anchor = min(visible, default=max(anchors, default=(before.y, before.y)))
    view.scroll_to(
        x=before.x, y=before.y + anchor[1] - anchor[0], animate=False, force=True, immediate=True
    )


def _restore_before_paint(view: StableScroll, before: _Position, request: int) -> None:
    """Layout and anchoring must finish inside the caller's repaint batch."""
    if not view.is_attached:
        return

    view.screen._refresh_layout()
    if view.scroll_request == request:
        _restore(view, before)
    view.screen._refresh_layout(scroll=True)


async def replace(view: StableScroll, widgets: abc.Iterable[Widget], preserve: bool) -> None:
    async with view.lock:
        before = _capture(view) if preserve else _Position((), 0, 0)
        request = view.scroll_request
        with view.app.batch_update():
            await view.remove_children()
            await view.mount_all(widgets)
            _restore_before_paint(view, before, request)


async def notice(view: StableScroll, message: str) -> None:
    async with view.lock:
        before = _capture(view)
        request = view.scroll_request
        with view.app.batch_update():
            await view.query(".brief-terminal-notice").remove()
            await view.mount(
                Static(message, classes="brief-terminal-notice", markup=False), before=0
            )
            _restore_before_paint(view, before, request)


def update(view: StableScroll, markdown: Markdown, text: str) -> None:
    before = _capture(view)
    request = view.scroll_request
    batch = contextlib.ExitStack()
    batch.enter_context(view.app.batch_update())
    completion = markdown.update(text)

    async def redrawn() -> None:
        with batch:
            await completion
            _restore_before_paint(view, before, request)

    if not view.app.call_later(redrawn):
        batch.close()
