"""`watch stop --self` stops only the caller's own waiters, and a stopped waiter says why."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from lemonaid.brief import attached, identity, waiters
from lemonaid.brief import store as brief_store
from lemonaid.inbox import db
from lemonaid.watch import registry, stop_cli, waiter_lock


def _briefed(channel: str, name: str, listed: str = "") -> Path:
    path = brief_store.briefs_dir() / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {name}\n\nStatus: working\n\n## Waiters\n\n{listed}")
    with db.connect() as conn:
        db.add(conn, channel, "")
        attached.attach(conn, channel, path)
        identity.ensure(conn, path)
    return path


def _start(channel: str, tmp_path: Path, *command: str) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-m", "lemonaid", *command],
        env={
            **os.environ,
            "LEMONAID_DB": str(tmp_path / "lemonaid.db"),
            "LEMONAID_CHANNEL": channel,
        },
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _registered(channel: str, kind: str) -> bool:
    for _ in range(200):
        if registry.mine(channel, kind):
            return True

        subprocess.run(["sleep", "0.05"])
    return False


def _stop(capsys, channel: str, *selector: str) -> str:
    parser = argparse.ArgumentParser()
    stop_cli.add_parser(parser.add_subparsers())
    args = parser.parse_args(["stop", "--self", "--channel", channel, *selector])
    assert stop_cli.run(args) == 0
    return capsys.readouterr().out


def test_stop_ends_only_the_callers_waiters_and_drops_their_entries(capsys, tmp_path):
    watched = tmp_path / "watched.md"
    watched.write_text("one\n")
    brief = _briefed("claude:mine", "mine", "- `lemonaid inbox watch --self`\n")
    _briefed("claude:other", "other")
    mine_inbox = _start("claude:mine", tmp_path, "inbox", "watch", "--self")
    mine_file = _start("claude:mine", tmp_path, "watch", "file", "--wait", str(watched))
    other_inbox = _start("claude:other", tmp_path, "inbox", "watch", "--self")
    try:
        assert _registered("claude:mine", "inbox")
        assert _registered("claude:mine", "file")
        assert _registered("claude:other", "inbox")
        assert any("watch file" in c for c in waiters.commands(brief.read_text()))

        assert f"pid {mine_file.pid}" in _stop(capsys, "claude:mine", "file", str(watched))
        _, err = mine_file.communicate(timeout=10)
        assert mine_file.returncode == 143
        assert "stopped by SIGTERM" in err
        assert f"lemonaid watch file --wait {watched}" in err
        assert mine_inbox.poll() is None

        assert f"pid {mine_inbox.pid}" in _stop(capsys, "claude:mine")
        assert mine_inbox.wait(timeout=10) == 143
        assert waiters.commands(brief.read_text()) == []

        assert other_inbox.poll() is None
        assert [w.pid for w in registry.mine("claude:other")] == [other_inbox.pid]
    finally:
        for process in (mine_inbox, mine_file, other_inbox):
            process.kill()
            process.wait()


def test_stop_without_a_waiter_says_so(capsys):
    _briefed("claude:mine", "mine")

    assert "No running waiter" in _stop(capsys, "claude:mine")


def test_an_entry_nobody_holds_is_never_signalled():
    entries = Path(os.environ["LEMONAID_STATE_DIR"]) / "waiters"
    entries.mkdir(parents=True, exist_ok=True)
    gone = entries / "999999.json"
    gone.write_text(
        json.dumps(
            {
                "pid": 999999,
                "channel": "claude:mine",
                "kind": "inbox",
                "targets": ["mine"],
                "command": "lemonaid inbox watch --self",
                "cwd": "/",
            }
        )
    )
    alive = entries / f"{os.getpid()}.json"  # this process, holding no lock on it
    alive.write_text(gone.read_text().replace("999999", str(os.getpid())))

    assert registry.mine("claude:mine") == []
    assert not gone.exists()
    assert alive.exists()
    alive.unlink()


def test_a_waiter_registers_only_while_it_runs():
    with registry.registered("pr", ("o/r#12",), "claude:mine", "lemonaid watch pr --wait 12") as w:
        assert registry.mine("claude:mine", "pr", "12") == [w]
        assert registry.mine("claude:mine", "pr", "13") == []
        assert waiter_lock.held(
            Path(os.environ["LEMONAID_STATE_DIR"]) / "waiters" / f"{w.pid}.json"
        )

    assert registry.mine("claude:mine") == []
