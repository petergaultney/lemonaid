"""Render a brief's detail view in the sidebar and popup.

The same field colours, model colour, and status headline fills, so
a brief in the sidebar or popup reads as the card opened up. What the worker
wrote stays Markdown, below.
"""

from rich.style import Style
from rich.text import Text

from ...brief import display, identity, render, status
from . import backend_indicators, brief_cards, brief_identity, utils

_SEPARATOR = Text(" · ", style=utils.FIELD_STYLES["backend"])
_HEADLINE_FILLS = {
    "alert": f"#ffffff on {brief_cards.ALERT_COLOR}",
    "blocked": f"#000000 on {utils.ATTENTION_COLOR}",
    "merge": f"#000000 on {brief_cards.MERGE_COLOR}",
    "approve": f"#ffffff on {brief_cards.APPROVE_COLOR}",
    "review": f"#ffffff on {brief_cards.REVIEW_COLOR}",
    "running": f"#ffffff on {brief_cards.RUNNING_COLOR}",
    "done": "#ffffff on #285995",
}


def _state_style(state: str, default: str = "") -> str:
    return brief_cards.status_text_style(state, default)


_PR_STYLES = {"open": "green", "draft": "bright_black", "merged": "magenta", "closed": "red"}
_SESSION_BAR = f"bold #000000 on {utils.ATTENTION_COLOR}"


def _edge() -> Text:
    return Text(f"{utils.HERE_BAR} ", style=utils.here_bar_style())


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
    left = (Text("● ", style=utils.unread_marker_style()) if unread else Text("")) + Text(
        name, style=f"bold {utils.FIELD_STYLES['name']}"
    )
    brief_name = identity.brief_name(section.lemon_id)
    suffix_start = len(left)
    if brief_name:
        left.append(" · ", style=utils.FIELD_STYLES["backend"])
        left.append(brief_name, style=utils.FIELD_STYLES["backend"])
    left.truncate(max(1, width - model.cell_len - 1), overflow="ellipsis")
    line = left + Text(" " * max(1, width - left.cell_len - model.cell_len)) + model
    if fill := _HEADLINE_FILLS.get(section.state):
        line.stylize(fill)
        if brief_name and len(left) > suffix_start:
            line.stylize(Style(color="bright_black"), suffix_start, len(left))

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
            (lemon.branch, "branch"),
            (lemon.directory, "cwd"),
        )
        if value
    )


def _state_line(section: render.Section, now_seconds: float, neutral_timing: bool = False) -> Text:
    prs = [
        Text(" ".join(part for part in (label, state) if part), style=_PR_STYLES.get(state, ""))
        for label, state in section.prs
    ]
    age_field = (
        "time_old" if neutral_timing or now_seconds - section.mtime >= 24 * 60 * 60 else "time"
    )
    return _SEPARATOR.join(
        [
            (
                Text(section.held, style=_state_style(section.held, "dim"))
                if section.held
                else Text(render.status_text(section), style=_state_style(section.state, "dim"))
            ),
            *(
                [
                    Text(
                        f"updated {status.age(now_seconds - section.mtime)}",
                        style=utils.FIELD_STYLES[age_field],
                    )
                ]
                if section.path
                else []
            ),
            *prs,
        ]
    )


def header(
    section: render.Section,
    in_session: bool,
    now_seconds: float,
    width: int,
    unread: bool = False,
    neutral_timing: bool = False,
) -> Text:
    """The project, when known; then name and model, where it runs, which lemon it is
    (`brief_identity`), and status, age and PRs.

    *unread* puts the inbox card's dot before the name.
    """
    body = max(1, width - 2)
    project = (
        [Text(section.project, style=f"bold {utils.FIELD_STYLES['cwd']}")]
        if section.project
        else []
    )
    lines = [
        *project,
        _headline(section, body, unread),
        _context(section, in_session),
        *brief_identity.lines(section, body),
    ]
    lines.append(_state_line(section, now_seconds, neutral_timing))
    for line in lines:
        line.truncate(body, overflow="ellipsis")

    return Text("\n").join(_edge() + line for line in lines)


def children(section: render.Section) -> Text:
    """A brief's children: their status, session name, and brief name."""
    width = max(len(child.state or "-") for child in section.children)
    return Text("\n").join(
        [
            Text("Children:", style="bold"),
            *(
                Text.assemble(
                    "  ",
                    (child.state or "-", _state_style(child.state, "dim")),
                    " " * (width - len(child.state or "-") + 2),
                    *(
                        [child.name, "  "]
                        if child.name != identity.brief_description(child.lemon_id)
                        else []
                    ),
                    *([brief_identity.id_text(child.lemon_id)] if child.lemon_id else []),
                )
                for child in section.children
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
