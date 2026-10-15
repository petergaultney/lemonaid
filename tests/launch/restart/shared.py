import dataclasses
import json
import time

from lemonaid.brief import attached, store
from lemonaid.inbox import db
from lemonaid.launch.restart import pane, process

SESSION = "01234567-1234-4321-9876-012345678901"
CHANNEL = "codex:" + SESSION
SOURCE = process.Identity(101, 100, "ttys001", "Thu Oct 15 12:00:00 2026", "/bin/codex")
ROOT = process.Identity(100, 99, "ttys001", "Thu Oct 15 11:00:00 2026", "/bin/zsh")
TARGET = pane.Pane("/tmp/test-restart.sock", "%1", "@1", "/dev/ttys001", 100, False, "/tmp")
SETTINGS = {
    "model": "gpt-6",
    "sandbox": "workspace-write",
    "approval": "on-request",
    "profile": "",
    "effort": "high",
    "provider": "openai",
    "argv": ["codex", "--no-daemon", "-m", "gpt-6", "-s", "workspace-write", "-a", "on-request"],
}


def setup(conn, tmp_path):
    path = store.briefs_dir() / "restart.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    lemon_id = store.new_lemon_id(path)
    path.write_text(f"# Restart\n\nLemon-ID: {lemon_id}\n\n## Now\n\nKeep working.\n")
    transcript = tmp_path / f"{SESSION}.jsonl"
    transcript.write_text(
        json.dumps({"type": "session_meta", "payload": {"id": SESSION}})
        + "\n"
        + json.dumps({"type": "event_msg", "payload": {"type": "task_complete"}})
        + "\n"
    )
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
            "session_path": str(transcript),
            "tty": TARGET.tty,
            "tmux_socket": TARGET.socket,
        },
    )
    attached.attach(conn, CHANNEL, path)
    conn.execute(
        "INSERT INTO harness_generations VALUES (?, ?, ?, ?, '', ?)",
        (
            CHANNEL,
            SESSION,
            json.dumps(dataclasses.asdict(SOURCE)),
            json.dumps(SETTINGS),
            time.time(),
        ),
    )
    conn.commit()
    return path, db.get_by_channel(conn, CHANNEL, unread_only=False), lemon_id, transcript


def plan(tmp_path):
    return {
        "channel": CHANNEL,
        "lemon_id": "restart.Brief",
        "session_id": SESSION,
        "harness": "codex",
        "cwd": str(tmp_path),
        "source": dataclasses.asdict(SOURCE),
        "root": dataclasses.asdict(ROOT),
        "pane": dataclasses.asdict(dataclasses.replace(TARGET, cwd=str(tmp_path))),
        "settings": SETTINGS,
        "force": False,
        "argv": ["codex", "resume", SESSION],
        "history": str(tmp_path / f"{SESSION}.jsonl"),
        "history_stamp": [0, 0],
        "waiters": [],
        "exit_option": "",
        "caller": [],
    }
