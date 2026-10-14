from textual.app import ComposeResult
from textual.content import Content
from textual.layout import Layout
from textual.style import Style
from textual.widgets._markdown import MarkdownTableContent


class _DocsTableContent(MarkdownTableContent):
    def __init__(self, headers: list[Content], rows: list[list[Content]]) -> None:
        super().__init__(headers, rows)
        self.styles.grid_columns = "1fr 1fr 18"

    def compose(self) -> ComposeResult:
        for widget in super().compose():
            if widget.name and widget.name.endswith(".1"):
                url = next(
                    (
                        span.style.link
                        for span in widget.content.spans
                        if isinstance(span.style, Style) and span.style.link
                    ),
                    "",
                )
                if url:
                    widget.tooltip = url
            yield widget

    def pre_layout(self, layout: Layout) -> None:
        super().pre_layout(layout)
        layout.auto_minimum = False
        layout.shrink = False


def content(headers: list[Content], rows: list[list[Content]]) -> MarkdownTableContent:
    widget = (
        _DocsTableContent
        if [header.plain.lower() for header in headers] == ["document", "purpose", "watch"]
        else MarkdownTableContent
    )
    return widget(headers, rows)
