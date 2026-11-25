"""A lemon's brief as its page shows it: the parts the inbox's brief pane draws, in the same
order and colors, so the browser reads like the tmux sidebar.

The pane's own drawing (status card, children, files) is Rich text, which goes to the page as
HTML with its colors inline; what the worker wrote stays Markdown for the page to render.
"""

import io
from collections import abc
from pathlib import Path

from rich import console, terminal_theme
from rich.text import Text

from ...brief import links, render
from ...inbox.tui.briefs import brief_detail

WIDTH = 80  # characters, when the page doesn't say how wide its brief pane is


def _html(text: Text, width: int) -> str:
    drawn = console.Console(
        record=True,
        width=width,
        file=io.StringIO(),
        force_terminal=True,
        color_system="truecolor",
    )
    drawn.print(text, soft_wrap=True)
    return drawn.export_html(theme=terminal_theme.MONOKAI, inline_styles=True, code_format="{code}")


def _section(
    section: render.Section,
    in_session: bool,
    now: float,
    vaults: abc.Collection[Path],
    width: int,
) -> dict:
    def marked(text: str) -> str:
        return links.linkify(text, vaults) if text else ""

    return {
        "card": _html(brief_detail.header(section, in_session, now, width), width),
        "summary": marked(section.summary),
        "summary_title": render.summary_title(section),
        "summary_open": section.summary_open,
        "needs": marked(render.needs(section, True)),
        "held": bool(section.held),
        "body": marked(section.body),
        "children": _html(brief_detail.children(section), width) if section.children else "",
        "tail": marked(section.tail),
    }


def drawn(shown: render.View, now: float, vaults: abc.Collection[Path], width: int = WIDTH) -> dict:
    """The page's brief, drawn *width* characters wide: a session bar, each section's parts, and
    the files they come from."""
    if not shown.sections:
        return {"fallback": links.linkify(render.to_markdown(shown, now), vaults)}

    return {
        "session": shown.header.removeprefix("# ").strip() if shown.header.startswith("# ") else "",
        "header": "" if shown.header.startswith("# ") else links.linkify(shown.header, vaults),
        "sections": [_section(s, shown.in_session, now, vaults, width) for s in shown.sections],
        "files": _html(brief_detail.files(shown), width),
    }
