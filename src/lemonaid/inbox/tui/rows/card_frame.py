"""Frame the current session within a card's existing gutter and separator."""

from rich.style import Style
from rich.text import Text

from ..utils import HERE_BAR


def _framed(lines: list[Text], width: int, style: str) -> list[Text]:
    # Reverse a lower-three-quarter block to draw the top quarter in the frame
    # color, with the remaining pixels inheriting the row background.
    return [
        *(
            Text.assemble(
                ("\u258c", style),
                line[1:],
                " " * max(0, width - line.cell_len),
                ("\u2590", style),
            )
            for line in lines[:-1]
        ),
        Text("\u2586" * (width + 1), style=Style.parse(style) + Style(reverse=True)),
    ]


def finished(
    lines: list[Text],
    width: int,
    frame_color: str,
    rail: str,
    end_rail: bool,
) -> list[Text]:
    if frame_color:
        lines = _framed(lines, width, frame_color)

    if rail:
        lines = [
            Text.assemble((HERE_BAR, rail)) + line
            if index < len(lines) - 1 or not end_rail
            else Text(" ") + line
            for index, line in enumerate(lines)
        ]
    return lines
