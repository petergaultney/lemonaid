#!/usr/bin/env python3
"""Stage an inbox of invented sessions on a throwaway tmux server, for screenshots.

    uv run scripts/demo-inbox.py            # left sidebar, cards
    uv run scripts/demo-inbox.py --top      # top strip, columns

Attaches a tmux server named `lemonaid-demo` with the scratch pane already
showing. It reads your own `~/.tmux.conf`, so the demo looks like your tmux
(set `LEMONAID_DEMO_NO_CONFIG=1` for tmux's stock defaults instead). Your
prefix detaches it as usual; `--kill` tears the server and its inbox down.

Everything it touches is its own: the inbox, config, state, briefs and message
inboxes all live under one scratch directory, and the server has its own socket,
so the real inbox is never read, written, or archived by the demo's watchers.
`scripts/demo-screenshot.py` renders the staged server to a PNG.
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

SERVER = "lemonaid-demo"
ROOT = Path(tempfile.gettempdir()) / "lemonaid-demo"
DB = ROOT / "demo.db"
BRIEFS = ROOT / "briefs"

# Set before any lemonaid import, so nothing can resolve a real path even
# transiently: seeding or archiving the wrong inbox is the one unrecoverable
# mistake this script could make. The demo server's panes get the same values.
ENVIRONMENT = {
    "LEMONAID_DB": str(DB),
    "LEMONAID_CONFIG": str(ROOT / "config.toml"),
    "LEMONAID_STATE_DIR": str(ROOT / "state"),
    "LEMONAID_BRIEFS_DIR": str(BRIEFS),
    "LEMONAID_MESSAGES_DIR": str(ROOT / "messages"),
}
os.environ.update(ENVIRONMENT)
# Nothing here should reach the tmux server this shell is in; the demo server is
# always named with `-L`, and attaching to it from inside tmux needs these unset.
os.environ.pop("TMUX", None)
os.environ.pop("TMUX_PANE", None)

# Brief-status cards are opt-in; the demo shows them, since they are what a
# session with a brief looks like.
_CONFIG = """\
[tui]
brief_status = true
"""

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
        "",
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
        "blocked",
    ),
    (
        "grocery-list-dedupe",
        "read",
        41 * _MINUTE,
        "codex",
        "src/pantry",
        "chore/dedupe",
        "Opened the PR. Nothing left to do until someone reviews it.",
        "waiting",
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
        "done",
    ),
    (
        "spice-rack-inventory",
        "read",
        5 * 60 * _MINUTE,
        "openclaw",
        "notes",
        "",
        "Synced - 7843 bytes, matching the corrected version.",
        "",
    ),
    (
        "leftovers-what-can-i-make",
        "read",
        6 * 60 * _MINUTE,
        "claude",
        "notes",
        "",
        "Here's what I can and can't tell you.",
        "",
    ),
]

# What each session's transcript would have named, so cards show a model rather
# than the provider fallback. OpenClaw's is left unknown: its fallback is the 🦞.
_MODELS = {
    "pantry-expiry-notifier": ("anthropic", "claude-opus-5-5"),
    "sourdough-hydration-calc": ("anthropic", "claude-opus-5-5"),
    "grocery-list-dedupe": ("openai", "gpt-5.6-sol"),
    "recipe-import-from-url": ("anthropic", "claude-fable-5-1"),
    "leftovers-what-can-i-make": ("anthropic", "claude-sonnet-5-5"),
}

# `## Now` for each brief status a session above carries.
_NOW = {
    "blocked": "### Needs you\n\n- Pick a rounding rule for hydration above 100%\n",
    "waiting": "### Waiting on\n\n- Review of the dedupe PR\n",
    "done": "### Done\n\n- Recipe import merged\n",
}


# The main panes end up in the same screenshot as the sidebar, so they show
# invented output too - a real shell would put a real prompt, path, and branch
# on display.
# The cards point at agent sessions, so the pane beside them shows one. Chrome
# copied from Claude Code's TUI - the glyphs are the real ones, hence the noqa;
# the content is the invented recipe project.
_CLAUDE = """\033[38;5;210m ▛▀▖▗▀▖\033[0m  \033[1mClaude Code\033[0m \033[2mv2.1.241\033[0m
\033[38;5;210m ▙▄▘▝▄▘\033[0m  \033[2mOpus 5.5 · ~/src/pantry\033[0m

\033[2m✻ Conversation compacted (ctrl+o for history)\033[0m

\033[38;5;114m⏺\033[0m The expiry check fired on the morning of, which is too late to
  act on. Moving it to three days out.

\033[38;5;114m⏺\033[0m \033[1mRead\033[0m(src/pantry/expiry.py)
  \033[2m⎿  Read 84 lines\033[0m

\033[38;5;114m⏺\033[0m \033[1mEdit\033[0m(src/pantry/expiry.py)
  \033[2m⎿  Updated with 2 additions and 2 removals\033[0m

\033[38;5;114m⏺\033[0m \033[1mBash\033[0m(uv run pytest tests/test_expiry.py -q)
  \033[2m⎿  12 passed in 0.31s\033[0m

\033[38;5;114m⏺\033[0m All four checks green. The notifier now fires 3 days out instead
  of on the morning of, which is what the yoghurt incident called for.

\033[2m─────────────────────────────────────────────────────────────────\033[0m

\033[38;5;110m›\033[0m \033[2mTry "add a test for the leap-year case"\033[0m

  \033[2mOpus 5.5 · feat/expiry-alerts · 34% context\033[0m"""  # noqa: RUF001

_PYTEST = """\033[2m$\033[0m uv run pytest -q
........................................................ [ 71%]
does.......                                              [100%]
\033[38;5;114m67 passed\033[0m in 2.14s"""


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


def _brief(name: str, status: str, modified: float) -> Path:
    path = BRIEFS / f"{name}.md"
    path.write_text(f"# {name}\n\nStatus: {status}\n\n## Now\n\n{_NOW[status]}")
    os.utime(path, (modified, modified))  # cards show the brief's age
    return path


def _seed() -> None:
    from lemonaid.brief import attached
    from lemonaid.inbox import db

    assert db.get_db_path() == DB, db.get_db_path()
    DB.parent.mkdir(parents=True, exist_ok=True)
    DB.unlink(missing_ok=True)
    shutil.rmtree(BRIEFS, ignore_errors=True)
    BRIEFS.mkdir()
    Path(ENVIRONMENT["LEMONAID_CONFIG"]).write_text(_CONFIG)
    now = time.time()
    with db.connect() as conn:
        for i, (name, status, age, backend, cwd, branch, message, brief) in enumerate(SESSIONS):
            channel = f"{backend}:demo-{i}"
            db.add(
                conn,
                channel,
                message,
                name,
                {
                    # Absolute, as a real hook records it: `fish_path` shortens
                    # `$HOME` to `~` and leaves an unexpanded `~/...` string as
                    # the unrecognisable `/s/pantry`.
                    "tty": f"/dev/ttys{900 + i}",  # far from the ptys the demo panes get
                    "cwd": str(Path.home() / cwd),
                    "git_branch": branch,
                    **(
                        {"model_provider": _MODELS[name][0], "model": _MODELS[name][1]}
                        if name in _MODELS
                        else {}
                    ),
                },
                switch_source="tmux",
                created_at=now - age,
                status=status,
            )
            if brief:
                attached.attach(conn, channel, _brief(name, brief, now - age))


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
    from lemonaid.tmux import scratch

    path = scratch.get_state_path() / f"tmux-scratch-{SERVER}-position"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(position)


def _kill() -> None:
    _tmux("kill-server")
    shutil.rmtree(ROOT, ignore_errors=True)
    print(f"killed {SERVER}, removed {ROOT}")


def _stage(position: str, attach: bool = True) -> None:
    # A previous run's `lma` would otherwise watch the new rows as they are
    # seeded, and the layout is decided when the pane is built, so a leftover
    # pane would render the previous position. Everything is torn down first.
    _tmux("kill-server")
    _seed()
    _position_state(position)

    _tmux(
        *_config_args(),
        "new-session",
        "-d",
        "-s",
        "demo",
        "-n",
        "pantry",
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
    for name, value in ENVIRONMENT.items():
        _tmux("set-environment", "-g", name, value)
    _tmux(
        "respawn-pane",
        "-k",
        "-c",
        str(Path.home()),
        "-t",
        "demo:pantry",
        *_show(_CLAUDE, "pantry"),
    )
    # Named, not indexed: `base-index` is a config setting, so :1 is the first
    # window on one server and the second on another.
    _tmux(
        "new-window", "-t", "demo", "-n", "tests", "-c", str(Path.home()), *_show(_PYTEST, "tests")
    )
    _tmux("set-window-option", "-t", "demo:tests", "automatic-rename", "off")
    _tmux("select-window", "-t", "demo:pantry")

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
        env={**os.environ, "TMUX": _socket()},
        capture_output=True,
    )
    time.sleep(2)
    # The cursor starts on the first row and would hide its brief colour; put it
    # on the session the main pane shows instead.
    scratch_pane = _tmux("show-options", "-gqv", "@lemonaid_scratch_pane").stdout.strip()
    _tmux("send-keys", "-t", scratch_pane, "Down", "Down")
    time.sleep(1)
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
