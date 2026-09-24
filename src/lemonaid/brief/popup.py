"""Showing a brief to a person: in a pager, and in a tmux popup around one."""

import re
import subprocess
import sys
from collections import abc

import rich.console
import rich.markdown
import rich.segment
import rich.style

from . import dismiss, target

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


def _less_command(quit_keys: abc.Iterable[str] = ()) -> list[str]:
    """A pager that closes on q, Escape, and each lesskey sequence in `quit_keys`.

    `--tilde` leaves the lines past the end of a short brief blank.
    """
    lesskey = ";".join([_LESSKEY_CONTENT, *(f"{seq} quit" for seq in quit_keys)])
    return ["less", "-R", "--tilde", f"--lesskey-content={lesskey}"]


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


def page(markdown: str, quit_keys: abc.Iterable[str] = ()) -> None:
    """Show Markdown rendered by Rich in an ANSI-aware pager."""
    console = rich.console.Console(force_terminal=True)
    with console.capture() as capture:
        console.print(rich.segment.Segments(_render_markdown(console, markdown)), end="")
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
        *(arg for path in found.attached for arg in ("--file", str(path))),
        *(arg for directory in found.dirs for arg in ("--dir", str(directory))),
        *(["--place", str(found.place)] if found.place else []),
        *(arg for name in found.names for arg in ("--name", name)),
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
