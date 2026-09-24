"""Showing a brief to a person: in a pager, and in a tmux popup around one."""

import re
import subprocess
import sys
from collections import abc
from pathlib import Path

import rich.console
import rich.markdown
import rich.segment
import rich.style

_MAX_POPUP_WIDTH = 140
_TMUX_QUERY_TIMEOUT_SECONDS = 0.5
_LESSKEY_CONTENT = r"#command;\e quit"
_STATUS_LINE = re.compile(
    r"^(?P<label>\s*Status:\s*)(?P<value>.*?)(?P<trailing>\s*)$", re.IGNORECASE
)
_STATUS_STYLES = {
    "working": rich.style.Style(color="yellow"),
    "done": rich.style.Style(color="green"),
    "blocked": rich.style.Style(color="red"),
}
_UNKNOWN_STATUS_STYLE = rich.style.Style(dim=True)


def _less_command() -> list[str]:
    """A pager whose two natural dismiss keys both close it.

    `--tilde` leaves the lines past the end of a short brief blank.
    """
    return ["less", "-R", "--tilde", f"--lesskey-content={_LESSKEY_CONTENT}"]


def _render_markdown(console: rich.console.Console, markdown: str) -> list[rich.segment.Segment]:
    """Render Markdown, colouring each brief status by its state."""
    rendered: list[rich.segment.Segment] = []
    for line in rich.segment.Segment.split_lines(console.render(rich.markdown.Markdown(markdown))):
        plain = "".join(segment.text for segment in line)
        match = _STATUS_LINE.fullmatch(plain)
        if match:
            value = match["value"]
            rendered.extend(
                [
                    rich.segment.Segment(match["label"], rich.style.Style(bold=True)),
                    rich.segment.Segment(
                        value,
                        _STATUS_STYLES.get(value.partition(" ")[0].lower(), _UNKNOWN_STATUS_STYLE),
                    ),
                    rich.segment.Segment(match["trailing"]),
                ]
            )
        else:
            rendered.extend(line)
        rendered.append(rich.segment.Segment.line())

    return rendered


def page(markdown: str) -> None:
    """Show Markdown rendered by Rich in an ANSI-aware pager."""
    console = rich.console.Console(force_terminal=True)
    with console.capture() as capture:
        console.print(rich.segment.Segments(_render_markdown(console, markdown)), end="")
    subprocess.run(_less_command(), input=capture.get(), text=True)


def popup_command(directory: Path, names: abc.Iterable[str]) -> list[str]:
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
        "--dir",
        str(directory),
        *(arg for name in names for arg in ("--name", name)),
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


def open_popup(directory: Path, names: abc.Iterable[str], title: str) -> None:
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
            f" {title.replace('#', '##')} ",
            # As separate arguments, tmux execs the command itself instead of
            # handing one string to default-shell, which need not be POSIX.
            *popup_command(directory, names),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
