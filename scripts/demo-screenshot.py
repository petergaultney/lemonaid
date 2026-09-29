#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyte>=0.8.2"]
# ///
"""Render the staged demo server to a PNG, as a terminal attached to it would show it.

    uv run scripts/demo-inbox.py --no-attach          # or --top
    uv run scripts/demo-screenshot.py docs/images/left-sidebar.png

A tmux client is attached in a pseudo-terminal, and what the server sends it is
fed to a terminal emulator (`pyte`), so the status line and pane borders come
out exactly as tmux drew them. The emulated screen becomes an HTML grid of fixed
cells, and headless Chrome, with a throwaway profile, screenshots that.
"""

import argparse
import fcntl
import html
import os
import pty
import select
import signal
import struct
import subprocess
import tempfile
import termios
import time
from pathlib import Path

import pyte

SERVER = "lemonaid-demo"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# A dark theme close to a default dark terminal profile.
_BACKGROUND = "#1e1e1e"
_FOREGROUND = "#d4d4d4"
_NAMED = {
    "black": "#000000",
    "red": "#cd3131",
    "green": "#0dbc79",
    "brown": "#e5e510",
    "blue": "#2472c8",
    "magenta": "#bc3fbc",
    "cyan": "#11a8cd",
    "white": "#e5e5e5",
    "brightblack": "#666666",
    "brightred": "#f14c4c",
    "brightgreen": "#23d18b",
    "brightbrown": "#f5f543",
    "brightblue": "#3b8eea",
    "brightmagenta": "#d670d6",
    "brightcyan": "#29b8db",
    "brightwhite": "#ffffff",
}
_CELL_WIDTH = 8.4  # px, at 14px Menlo
_CELL_HEIGHT = 17


class _Screen(pyte.Screen):
    """pyte's screen, without answering queries tmux sends an attached terminal.

    tmux asks with private-mode sequences (`CSI ? n`) that pyte's own handlers
    do not accept, and no answer is needed to draw.
    """

    def report_device_status(self, *args: int, **kwargs: object) -> None:
        pass


def _colour(value: str, default: str) -> str:
    if value == "default":
        return default

    if value in _NAMED:
        return _NAMED[value]

    return f"#{value}"


def _capture(columns: int, rows: int, settle: float) -> pyte.Screen:
    """The screen a `columns` x `rows` terminal shows once attached for `settle` seconds."""
    screen = _Screen(columns, rows)
    stream = pyte.ByteStream(screen)
    env = {
        **{k: v for k, v in os.environ.items() if k not in {"TMUX", "TMUX_PANE"}},
        "TERM": "xterm-256color",
        "COLORTERM": "truecolor",
    }
    pid, fd = pty.fork()
    if pid == 0:
        os.execvpe("tmux", ["tmux", "-L", SERVER, "attach", "-t", "demo"], env)

    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, columns, 0, 0))
    os.kill(pid, signal.SIGWINCH)
    deadline = time.monotonic() + settle
    while (remaining := deadline - time.monotonic()) > 0:
        ready, _, _ = select.select([fd], [], [], remaining)
        if ready:
            try:
                stream.feed(os.read(fd, 65536))
            except OSError:
                break

    os.kill(pid, signal.SIGHUP)  # the client exits; the server and its panes stay
    os.close(fd)
    os.waitpid(pid, 0)
    return screen


def _cell_html(char: pyte.screens.Char, wide: bool) -> str:
    foreground = _colour(char.fg, _FOREGROUND)
    background = _colour(char.bg, _BACKGROUND)
    if char.reverse:
        foreground, background = background, foreground
    styles = [f"color:{foreground}", f"background:{background}"]
    if char.bold:
        styles.append("font-weight:bold")
    if char.italics:
        styles.append("font-style:italic")
    if char.underscore:
        styles.append("text-decoration:underline")
    classes = "c w" if wide else "c"
    text = html.escape(char.data) if char.data.strip() else "&nbsp;"
    return f'<span class="{classes}" style="{";".join(styles)}">{text}</span>'


def _row_html(screen: pyte.Screen, y: int) -> str:
    line = screen.buffer[y]
    cells = []
    x = 0
    while x < screen.columns:
        char = line[x]
        # pyte stores a wide character in its first cell and leaves the second
        # empty; the pair is drawn as one double-width cell.
        wide = x + 1 < screen.columns and line[x + 1].data == "" and char.data != ""
        cells.append(_cell_html(char, wide))
        x += 2 if wide else 1
    return f'<div class="r">{"".join(cells)}</div>'


def _page(screen: pyte.Screen) -> str:
    rows = "\n".join(_row_html(screen, y) for y in range(screen.lines))
    return f"""<!doctype html><meta charset="utf-8"><style>
body {{ margin: 0; background: {_BACKGROUND}; }}
.r {{ height: {_CELL_HEIGHT}px; white-space: pre; overflow: hidden; }}
.c {{ display: inline-block; width: {_CELL_WIDTH}px; height: {_CELL_HEIGHT}px;
     line-height: {_CELL_HEIGHT}px; overflow: visible; vertical-align: top;
     font: 14px Menlo, "STIX Two Math", monospace; }}
.w {{ width: {2 * _CELL_WIDTH}px; font-family: Menlo, "Apple Color Emoji", monospace; }}
</style><body>{rows}</body>"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="PNG to write")
    parser.add_argument("--columns", type=int, default=150)
    parser.add_argument("--rows", type=int, default=40)
    # Past the inbox's first 10 seconds, when key hints hold its bottom row.
    parser.add_argument("--settle", type=float, default=12.0, help="seconds to let it draw")
    args = parser.parse_args()

    screen = _capture(args.columns, args.rows, args.settle)
    with tempfile.TemporaryDirectory() as scratch:
        page = Path(scratch) / "screen.html"
        page.write_text(_page(screen))
        width = round(args.columns * _CELL_WIDTH)
        height = args.rows * _CELL_HEIGHT
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.unlink(missing_ok=True)
        # Headless Chrome on macOS can keep running after it writes the file, so
        # the file appearing is the signal that it is done.
        chrome = subprocess.Popen(
            [
                CHROME,
                "--headless=new",
                f"--user-data-dir={Path(scratch) / 'profile'}",
                "--hide-scrollbars",
                "--force-device-scale-factor=2",
                f"--window-size={width},{height}",
                f"--screenshot={args.output.resolve()}",
                page.as_uri(),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.monotonic() + 60
        while not args.output.exists() and chrome.poll() is None:
            if time.monotonic() > deadline:
                chrome.kill()
                raise SystemExit("Chrome wrote no screenshot within 60 seconds")
            time.sleep(0.2)
        time.sleep(0.5)  # let it finish writing
        chrome.terminate()
        chrome.wait()
    if not args.output.exists():
        raise SystemExit(f"Chrome exited ({chrome.returncode}) without writing {args.output}")

    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
