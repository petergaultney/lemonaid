"""A brief section's identity drawn the way the inbox draws that lemon's card.

The same field colours, model colour, and status headline fills, so
a brief in the sidebar or popup reads as the card opened up. What the worker
wrote stays Markdown, below.
"""

from rich.text import Text

from ...brief import display, render, status
from . import backend_indicators, brief_cards, utils

_SEPARATOR = Text(" · ", style=utils.FIELD_STYLES["backend"])
_HEADLINE_FILLS = {
    "alert": f"#ffffff on {brief_cards.ALERT_COLOR}",
    "blocked": f"#000000 on {utils.ATTENTION_COLOR}",
    "merge": f"#000000 on {brief_cards.MERGE_COLOR}",
    "done": "#ffffff on #285995",
}
_STATE_STYLES = {
    "alert": "bold #ff5c5c",
    "blocked": f"bold {utils.ATTENTION_COLOR}",
    "merge": f"bold {brief_cards.MERGE_COLOR}",
    "done": "bold #6f9fe0",
    "working": "bold",
    "waiting": "bright_black",
}
_PR_STYLES = {"open": "green", "draft": "bright_black", "merged": "magenta", "closed": "red"}
_SESSION_BAR = f"bold #000000 on {utils.ATTENTION_COLOR}"


def _edge() -> Text:
    return Text(f"{utils.HERE_BAR} ", style=utils.HERE_BAR_STYLE)


def _headline(section: render.Section, width: int, unread: bool) -> Text:
    lemon = section.lemon
    name = (
        " ".join(part for part in (lemon.emoji, lemon.name or lemon.backend) if part)
        if lemon
        else section.title
    )
    model = Text(
        (lemon.model or lemon.backend) if lemon else "",
        style=backend_indicators.provider_style(lemon.backend.lower(), lemon.provider)
        if lemon
        else "",
    )
    left = (Text("● ", style=utils.UNREAD_MARKER_STYLE) if unread else Text("")) + Text(
        name, style=f"bold {utils.FIELD_STYLES['name']}"
    )
    left.truncate(max(1, width - model.cell_len - 1), overflow="ellipsis")
    line = left + Text(" " * max(1, width - left.cell_len - model.cell_len)) + model
    if fill := _HEADLINE_FILLS.get(section.state):
        line.stylize(fill)

    return line


def _context(section: render.Section, in_session: bool) -> Text:
    lemon = section.lemon
    if not lemon:
        return Text("")

    location = (
        f"w{lemon.tmux_window}"
        if in_session
        else ":".join(part for part in (lemon.tmux_session, lemon.tmux_window) if part)
    )
    return _SEPARATOR.join(
        Text(value, style=utils.FIELD_STYLES[field])
        for value, field in (
            (location, "backend"),
            (lemon.directory, "cwd"),
            (lemon.branch, "branch"),
        )
        if value
    )


def _state_line(section: render.Section, now_seconds: float) -> Text:
    prs = [
        Text(" ".join(part for part in (label, state) if part), style=_PR_STYLES.get(state, ""))
        for label, state in section.prs
    ]
    return _SEPARATOR.join(
        [
            Text(render.status_text(section), style=_STATE_STYLES.get(section.state, "dim")),
            *(
                [Text(f"updated {status.age(now_seconds - section.mtime)}", style="dim")]
                if section.path
                else []
            ),
            *prs,
        ]
    )


def header(
    section: render.Section, in_session: bool, now_seconds: float, width: int, unread: bool = False
) -> Text:
    """Three lines: name and model, where it runs, then status, age and PRs.

    *unread* puts the inbox card's dot before the name.
    """
    body = max(1, width - 2)
    lines = [_headline(section, body, unread), _context(section, in_session)]
    if section.state == "waiting":
        for line in lines:
            line.stylize("dim")

    lines.append(_state_line(section, now_seconds))
    for line in lines[1:]:
        line.truncate(body, overflow="ellipsis")

    return Text("\n").join(_edge() + line for line in lines)


def children(section: render.Section) -> Text:
    """A brief's children, one per line: its status coloured as on its card, then its name."""
    width = max(len(state or "-") for state, _ in section.children)
    return Text("\n").join(
        [
            Text("Children:", style="bold"),
            *(
                Text.assemble(
                    "  ",
                    (state or "-", _STATE_STYLES.get(state, "dim")),
                    " " * (width - len(state or "-") + 2),
                    name,
                )
                for state, name in section.children
            ),
        ]
    )


def session_bar(header: str, width: int) -> Text:
    """A session's name from a view's `# ...` header, as a bar across the width."""
    name = header.removeprefix("# ").strip()
    return Text(name.center(max(width, len(name))), style=_SESSION_BAR)


def files(shown: render.View) -> Text:
    """Each brief's path, dimmed: the card above already says how old it is."""
    return Text(
        "\n".join(
            " · ".join(
                part
                for part in (
                    f"w{s.lemon.tmux_window}" if shown.in_session and s.lemon else "",
                    display.home_path(s.path),
                )
                if part
            )
            for s in shown.sections
            if s.path
        ),
        style="dim",
    )
