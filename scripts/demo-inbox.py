#!/usr/bin/env python3
"""Stage an inbox of invented sessions on a throwaway tmux server, for screenshots.

    uv run scripts/demo-inbox.py            # left sidebar, cards
    uv run scripts/demo-inbox.py --top      # top strip, columns

Attaches a tmux server named `lemonaid-demo` with the scratch pane already
showing. It reads your own `~/.tmux.conf`, so the demo looks like your tmux
(set `LEMONAID_DEMO_NO_CONFIG=1` for tmux's stock defaults instead). Your
prefix detaches it as usual; `--kill` tears the server and its inbox down.

Everything it touches is its own: `LEMONAID_DB` points the inbox at a scratch
file and the server has its own socket, so the real inbox is never read, written,
or archived by the demo's watchers.
"""

import argparse
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

SERVER = "lemonaid-demo"
DB = Path(tempfile.gettempdir()) / "lemonaid-demo" / "demo.db"

# Ages, not timestamps: the inbox sorts unread first and then by recency, and a
# screenshot wants that ordering to look like an afternoon's work.
#
# Invented sessions on an invented project. These end up in screenshots, so
# nothing here should resemble a real repo, branch, or path.
_MINUTE = 60
SESSIONS = [
    (
        "pantry-expiry-notifier",
        "unread",
        4 * _MINUTE,
        "claude",
        "src/pantry",
        "feat/expiry-alerts",
        "All four checks green. The notifier now fires 3 days out instead of "
        "on the morning of, which is what the yoghurt incident called for.",
    ),
    (
        "sourdough-hydration-calc",
        "unread",
        22 * _MINUTE,
        "claude",
        "src/breadbox",
        "fix/baker-percentage",
        "Found the bug: `hydration()` divides by total dough weight rather "
        "than flour weight, so every loaf above 70% came out as 41%.",
    ),
    (
        "grocery-list-dedupe",
        "read",
        41 * _MINUTE,
        "codex",
        "src/pantry",
        "chore/dedupe",
        "Working...",
    ),
    (
        "recipe-import-from-url",
        "read",
        3 * 60 * _MINUTE,
        "claude",
        "src/cookbook",
        "main",
        "Done. Handles JSON-LD, microdata, and the three blog themes that "
        "put the ingredients in a table. Falls back to asking rather than guessing.",
    ),
    (
        "spice-rack-inventory",
        "read",
        5 * 60 * _MINUTE,
        "openclaw",
        "notes",
        "",
        "Synced - 7843 bytes, matching the corrected version.",
    ),
    (
        "leftovers-what-can-i-make",
        "read",
        6 * 60 * _MINUTE,
        "claude",
        "notes",
        "",
        "Here's what I can and can't tell you.",
    ),
]


# The main panes end up in the same screenshot as the sidebar, so they show
# invented output too - a real shell would put a real prompt, path, and branch
# on display.
_GIT_LOG = """$ git log --oneline -8
8f2a1c4 (HEAD -> feat/expiry-alerts) notify three days out, not on the day
1d9e07b pantry: read expiry from the label scan when there is one
6b3c882 fix hydration() to divide by flour weight, not dough weight
44a1f5e cookbook: import recipes from JSON-LD and microdata
90ce713 grocery list: fold duplicate entries on normalised names
2ef4a06 spice rack: seed the inventory from last year's notes
b7d1e59 pantry: first pass at an expiry model
0c5a3f8 initial commit"""

_PYTEST = """$ uv run pytest -q
........................................................ [ 71%]
does.......                                              [100%]
67 passed in 2.14s"""


def _show(text: str, title: str) -> list[str]:
    """A command that prints `text` and then holds the pane open.

    The demo panes run this instead of a shell. A real shell would put a real
    prompt, path, and branch on screen next to the sidebar - which is the thing
    a public screenshot must not contain - and the interactive shell here is
    xonsh, which does not read POSIX heredocs anyway.
    """
    # The pane title is what a window-status format falls back to for an
    # interpreter process, and its default is the hostname - which is the last
    # identifying thing left in a screenshot of this.
    script = f"print('\\033]2;{title}\\007' + {text!r}); import time; time.sleep(2**31)"
    return [sys.executable, "-c", script]


def _seed() -> None:
    # Set before the import so nothing can resolve the real inbox path, even
    # transiently: seeding the wrong database is the one unrecoverable mistake
    # this script could make.
    os.environ["LEMONAID_DB"] = str(DB)
    from lemonaid.inbox import db

    assert db.get_db_path() == DB, db.get_db_path()
    DB.parent.mkdir(parents=True, exist_ok=True)
    DB.unlink(missing_ok=True)
    now = time.time()
    with db.connect() as conn:
        for i, (name, status, age, backend, cwd, branch, message) in enumerate(SESSIONS):
            db.add(
                conn,
                f"{backend}:demo-{i}",
                message,
                name,
                {
                    # Absolute, as a real hook records it: `fish_path` shortens
                    # `$HOME` to `~` and leaves an unexpanded `~/...` string as
                    # the unrecognisable `/s/pantry`.
                    "tty": f"/dev/ttys{100 + i}",
                    "cwd": str(Path.home() / cwd),
                    "git_branch": branch,
                },
                switch_source="tmux",
                created_at=now - age,
                status=status,
            )


def _tmux(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["tmux", "-L", SERVER, *args], capture_output=True, text=True)


def _config_args() -> list[str]:
    """`-f` for the demo server: your own `.tmux.conf` unless told otherwise.

    A screenshot of a server running tmux's built-in defaults doesn't look like
    the thing being demonstrated - windows start at 0, the status bar is the
    stock green - so the demo reads the same config as everything else.
    """
    if os.environ.get("LEMONAID_DEMO_NO_CONFIG"):
        return ["-f", "/dev/null"]

    conf = Path.home() / ".tmux.conf"
    return ["-f", str(conf)] if conf.exists() else []


def _socket() -> str:
    """`$TMUX` for the demo server, which is how the CLI finds it."""
    out = _tmux("display-message", "-p", "#{socket_path}").stdout.strip()
    return f"{out},0,0"


def _position_state(position: str) -> None:
    """Write the position this server will start with, before anything reads it."""
    os.environ["TMUX"] = ""  # state paths key off the server name, not this shell's
    from lemonaid.tmux import scratch

    path = scratch.get_state_path() / f"tmux-scratch-{SERVER}-position"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(position)


def _kill() -> None:
    _tmux("kill-server")
    DB.unlink(missing_ok=True)
    os.environ["TMUX"] = ""
    from lemonaid.tmux import scratch

    for stale in scratch.get_state_path().glob(f"tmux-scratch-{SERVER}-*"):
        stale.unlink(missing_ok=True)
    print(f"killed {SERVER}, removed {DB} and its state files")


def _stage(position: str, attach: bool = True) -> None:
    _seed()
    _tmux("kill-server")
    # The layout is decided when the pane is built, so a leftover pane from a
    # previous run would render the previous position. Everything is torn down.
    _position_state(position)

    _tmux(
        *_config_args(),
        "new-session",
        "-d",
        "-s",
        "demo",
        "-n",
        "cookbook",
        "-c",
        str(Path.home()),
        "-x",
        "200",
        "-y",
        "50",
    )
    # Otherwise the window takes its name from whatever last ran in it, which in
    # a freshly-staged demo is the staging command.
    _tmux("set-window-option", "-t", "demo", "automatic-rename", "off")
    # The pane the CLI spawns is a child of the server, so this is what points
    # the demo's own `lma` at the demo inbox rather than the real one.
    _tmux("set-environment", "-g", "LEMONAID_DB", str(DB))
    _tmux(
        "respawn-pane",
        "-k",
        "-c",
        str(Path.home()),
        "-t",
        "demo:cookbook",
        *_show(_GIT_LOG, "cookbook"),
    )
    # Named, not indexed: `base-index` is a config setting, so :1 is the first
    # window on one server and the second on another.
    _tmux(
        "new-window", "-t", "demo", "-n", "tests", "-c", str(Path.home()), *_show(_PYTEST, "tests")
    )
    _tmux("set-window-option", "-t", "demo:tests", "automatic-rename", "off")
    _tmux("select-window", "-t", "demo:tests")

    # Created through the CLI so the demo exercises the real path - position,
    # sizing, and the follow hooks all come from the code under review.
    subprocess.run(
        [
            sys.executable,
            "-m",
            "lemonaid.cli",
            "tmux",
            "scratch",
            "--follow",
            f"--position={position}",
        ],
        env={**os.environ, "TMUX": _socket(), "LEMONAID_DB": str(DB)},
        capture_output=True,
    )
    time.sleep(2)
    print(f"staged on tmux -L {SERVER} ({position}).")
    if attach:
        print("attaching; Ctrl-b d to detach.")
        os.execvp("tmux", ["tmux", "-L", SERVER, "attach", "-t", "demo"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top", action="store_true", help="top strip instead of left sidebar")
    parser.add_argument("--kill", action="store_true", help="tear down the server and its inbox")
    parser.add_argument("--no-attach", action="store_true", help="stage it but stay in this shell")
    args = parser.parse_args()

    if args.kill:
        _kill()
        return

    _stage("top" if args.top else "left", attach=not args.no_attach)


if __name__ == "__main__":
    main()
