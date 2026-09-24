"""Showing a brief to a person: in a pager, and in a tmux popup around one."""

import shutil
import subprocess
import sys
import tempfile
from collections import abc
from pathlib import Path

import rich.console
import rich.markdown

_MAX_POPUP_WIDTH = 140
_TMUX_QUERY_TIMEOUT_SECONDS = 0.5
_LESSKEY_CONTENT = r"#command;\e quit"


def _less_command() -> list[str]:
    """A pager whose two natural dismiss keys both close it."""
    return ["less", "-R", f"--lesskey-content={_LESSKEY_CONTENT}"]


def page(markdown: str) -> None:
    """Show markdown in a pager, rendered by `glow` when it is installed."""
    glow = shutil.which("glow")
    if not glow:
        console = rich.console.Console(force_terminal=True)
        with console.capture() as capture:
            console.print(rich.markdown.Markdown(markdown))
        subprocess.run(_less_command(), input=capture.get(), text=True)
        return

    # A file rather than stdin: glow picks its light or dark style from the
    # terminal, which it can only query when stdin is still the tty.
    with tempfile.NamedTemporaryFile("w", suffix=".md") as f:
        f.write(markdown)
        f.flush()
        subprocess.run([glow, "-p", f.name])


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
