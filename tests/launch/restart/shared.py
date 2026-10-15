import dataclasses

from lemonaid.brief import attached, store
from lemonaid.inbox import db
from lemonaid.launch.restart import pane, process, state

SESSION = "01234567-1234-4321-9876-012345678901"
CHANNEL = "codex:" + SESSION
SOURCE = process.Identity(101, 100, "ttys001", "Thu Oct 15 12:00:00 2026", "/bin/codex")
ROOT = process.Identity(100, 99, "ttys001", "Thu Oct 15 11:00:00 2026", "/bin/zsh")
TARGET = pane.Pane("/tmp/test-restart.sock", "%1", "@1", "/dev/ttys001", 100, False, "/tmp")


def setup(conn, tmp_path):
    path = store.briefs_dir() / "restart.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    lemon_id = store.new_lemon_id(path)
    path.write_text(f"# Restart\n\nLemon-ID: {lemon_id}\n\n## Now\n\nKeep working.\n")
    conn.execute("INSERT INTO lemon_identities VALUES (?, ?)", (str(path), lemon_id))
    db.add(
        conn,
        CHANNEL,
        "Keep this",
        name="Manual",
        status="read",
        switch_source="tmux",
        metadata={
            "cwd": str(tmp_path),
            "session_id": SESSION,
            "tty": TARGET.tty,
            "tmux_socket": TARGET.socket,
        },
    )
    attached.attach(conn, CHANNEL, path)
    state.write(
        "native-" + state.key(CHANNEL) + ".json",
        {"session_id": SESSION, "identity": dataclasses.asdict(SOURCE)},
    )
    conn.commit()
    return path, lemon_id


def plan():
    return {
        "channel": CHANNEL,
        "lemon_id": "restart.Test",
        "source": dataclasses.asdict(SOURCE),
        "pane": dataclasses.asdict(TARGET),
        "root": dataclasses.asdict(ROOT),
        "force": False,
        "line": "codex resume " + SESSION,
        "environment": {},
        "cwd": "/tmp",
        "exit_option": "",
    }
