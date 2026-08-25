#!/usr/bin/env python3
"""Stage an inbox of invented sessions on a throwaway tmux server, for screenshots.

    uv run scripts/demo-inbox.py            # left sidebar, cards
    uv run scripts/demo-inbox.py --top      # top strip, columns

Attaches a tmux server named `lemonaid-demo` with the scratch pane already
showing. `Ctrl-b d` detaches; `--kill` tears the server and its inbox down.

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
_MINUTE = 60
SESSIONS = [
    (
        "tars-chat-observability",
        "unread",
        4 * _MINUTE,
        "claude",
        "~/w/d/t/live-observability",
        "tars/live-observability",
        "All four PRs green - #5343's last check passed.",
    ),
    (
        "protostellar-tenant-views",
        "unread",
        22 * _MINUTE,
        "claude",
        "~/w/ds-monorepo",
        "protostellar/tenant-views",
        "Blocking bug found: `Unmemoized.invoke()` is not bound to the invocation "
        "that produced it, so the memoized result lands under the wrong key.",
    ),
    (
        "obs-red-team",
        "read",
        41 * _MINUTE,
        "codex",
        "~/w/d/t/l/protostellar",
        "tars/live-observability",
        "Working...",
    ),
    (
        "relay-single-file-datadog-monitor",
        "read",
        3 * 60 * _MINUTE,
        "claude",
        "~/w/d/main",
        "main",
        "Done. Wrote `~/work/vault/th/datadog.md` with the full reference "
        "(tokens, monitor YAML locations, apply script, On-Call routing details).",
    ),
    (
        "openclaw-upgrade",
        "read",
        5 * 60 * _MINUTE,
        "openclaw",
        "~/trove",
        "",
        "Synced - 7843 bytes, matching the corrected version.",
    ),
    (
        "relay-debug-hq",
        "read",
        6 * 60 * _MINUTE,
        "claude",
        "~/trove",
        "",
        "Here's what I can and can't tell you.",
    ),
]


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
                {"tty": f"/dev/ttys{100 + i}", "cwd": cwd, "git_branch": branch},
                switch_source="tmux",
                created_at=now - age,
                status=status,
            )


def _tmux(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["tmux", "-L", SERVER, *args], capture_output=True, text=True)


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

    _tmux("-f", "/dev/null", "new-session", "-d", "-s", "demo", "-x", "200", "-y", "50")
    # The pane the CLI spawns is a child of the server, so this is what points
    # the demo's own `lma` at the demo inbox rather than the real one.
    _tmux("set-environment", "-g", "LEMONAID_DB", str(DB))
    _tmux("send-keys", "-t", "demo", "git log --oneline -12", "Enter")
    _tmux("new-window", "-t", "demo", "-n", "tests")
    _tmux("select-window", "-t", "demo:1")

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
