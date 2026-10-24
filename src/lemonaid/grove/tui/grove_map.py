"""The grove's picture as a Textual widget, which knows what each of its cells reaches."""

from textual.strip import Strip
from textual.widget import Widget

from ..draw import canvas


class GroveMap(Widget):
    DEFAULT_CSS = "GroveMap { width: 100%; height: 100%; }"

    def __init__(self) -> None:
        super().__init__()
        self.picture: canvas.Canvas | None = None

    def render_line(self, y: int) -> Strip:
        if self.picture is None or y >= self.picture.height:
            return Strip.blank(self.size.width)

        return Strip(canvas.line_segments(self.picture.rows[y]), self.picture.width)

    def target_at(self, x: int, y: int) -> tuple[str, ...]:
        if self.picture is None or not (
            0 <= y < self.picture.height and 0 <= x < self.picture.width
        ):
            return ()

        return self.picture.rows[y][x].target
