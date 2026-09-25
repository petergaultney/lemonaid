"""Showing a brief to a person: in a pager, and in a tmux popup around one."""

import subprocess
import sys
from collections import abc

import rich.console
import rich.markdown
import rich.rule
import rich.text
import rich.theme

from ..inbox.tui import brief_card, utils
from . import dismiss, links, render, target

_MAX_POPUP_WIDTH = 140
_TMUX_QUERY_TIMEOUT_SECONDS = 0.5
_LESSKEY_CONTENT = r"#command;\e quit"
# A lemon's Needs block in the colour the inbox uses for what wants you, and
# links in their own colour.
_THEME = rich.theme.Theme(
    {
        "markdown.block_quote": utils.ATTENTION_COLOR,
        "markdown.link": f"underline {utils.LINK_COLOR}",
    }
)


def _less_command(quit_keys: abc.Iterable[str] = ()) -> list[str]:
    """A pager that closes on q, Escape, and each lesskey sequence in `quit_keys`.

    `--tilde` leaves the lines past the end of a short brief blank.
    """
    lesskey = ";".join([_LESSKEY_CONTENT, *(f"{seq} quit" for seq in quit_keys)])
    return ["less", "-R", "--tilde", f"--lesskey-content={lesskey}"]


def _renderables(shown: render.View, now: float, width: int) -> list[rich.console.RenderableType]:
    """The view as the inbox would draw it: a session bar, then a card and its brief per lemon."""
    if not shown.sections:
        return [rich.markdown.Markdown(links.linkify(render.to_markdown(shown, now)))]

    gap = rich.text.Text("")
    rule = rich.rule.Rule(style="bright_black")
    top = (
        [brief_card.session_bar(shown.header, width), gap]
        if shown.header.startswith("# ")
        else [rich.markdown.Markdown(shown.header), gap]
        if shown.header
        else []
    )
    sections = [
        part
        for i, section in enumerate(shown.sections)
        for part in (
            *([gap, rule, gap] if i else []),
            brief_card.header(section, shown.in_session, now, width),
            *([rich.markdown.Markdown(links.linkify(section.body))] if section.body else []),
        )
    ]
    return [*top, *sections, gap, rule, brief_card.files(shown)]


def page(shown: render.View, now: float, quit_keys: abc.Iterable[str] = ()) -> None:
    """Show a view rendered by Rich in an ANSI-aware pager."""
    console = rich.console.Console(force_terminal=True, theme=_THEME)
    with console.capture() as capture:
        for renderable in _renderables(shown, now, console.width):
            console.print(renderable)
    subprocess.run(_less_command(quit_keys), input=capture.get(), text=True)


def popup_command(found: target.Target, quit_keys: abc.Iterable[str] = ()) -> list[str]:
    """The command a popup runs: this same lemonaid, paging one directory's brief.

    Everything it needs is in its arguments, since a popup inherits the tmux
    server's environment rather than the caller's.
    """
    return [
        sys.executable,
        "-m",
        "lemonaid.cli",
        "brief",
        "show",
        "--target",
        target.to_json(found),
        *(arg for seq in quit_keys for arg in ("--dismiss", seq)),
        "--page",
    ]


def _client_width() -> int | None:
    """Width of the client that invoked the popup, when tmux can answer."""
    try:
        result = subprocess.run(
            ["tmux", "display-message", "-p", "#{client_width}"],
            capture_output=True,
            text=True,
            check=True,
            timeout=_TMUX_QUERY_TIMEOUT_SECONDS,
        )
        return int(result.stdout.strip())
    except (OSError, ValueError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None


def _popup_width(client_width: int | None) -> str:
    """Keep the former 90% width, but stop growing past readable line lengths."""
    if client_width is None:
        return str(_MAX_POPUP_WIDTH)
    return str(min(_MAX_POPUP_WIDTH, max(1, client_width * 9 // 10)))


def open_popup(found: target.Target) -> None:
    """Open a popup over the calling client showing where a place's work stands.

    Never targets the lemon's own session, so the popup appears wherever the
    person asking is looking. Returns without waiting for the popup to close.
    """
    subprocess.Popen(
        [
            "tmux",
            "display-popup",
            "-E",
            "-w",
            _popup_width(_client_width()),
            "-h",
            "85%",
            "-S",
            "fg=yellow",
            "-T",
            # -T is a format, where a bare # starts a variable.
            f" {found.title.replace('#', '##')} ",
            # As separate arguments, tmux execs the command itself instead of
            # handing one string to default-shell, which need not be POSIX.
            *popup_command(found, dismiss.bound_sequences()),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
