"""Bare CLI handoff finds one stopped source and runs the target on its controlling TTY."""

import os
import pty
import select
import shutil
import signal
import subprocess
import sys
import time
from contextlib import suppress
from pathlib import Path
from types import SimpleNamespace

import pytest

from lemonaid.brief import handoff_shell
from lemonaid.inbox import db


def _ps(stdout: str, returncode: int = 0, stderr: str = ""):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def test_stopped_job_on_tty_selects_one_harness_group(monkeypatch):
    calls = []

    def run(args, **_kwargs):
        calls.append(args)
        if "-t" in args:
            return _ps("401 401 T Mon Oct 5 20:00:00 2026 /usr/bin/claude\n")
        return _ps("401 ttys2 T Mon Oct 5 20:00:00 2026 /usr/bin/claude\n")

    monkeypatch.setattr(handoff_shell.subprocess, "run", run)
    monkeypatch.setattr(handoff_shell.os, "getpgrp", lambda: 999)

    assert handoff_shell.stopped_job_on_tty("/dev/ttys2", "claude") == (
        401,
        401,
        "ttys2",
        "Mon Oct 5 20:00:00 2026",
    )
    assert len(calls) == 2


def test_stopped_job_on_tty_refuses_multiple_groups(monkeypatch):
    monkeypatch.setattr(
        handoff_shell.subprocess,
        "run",
        lambda *_args, **_kwargs: _ps(
            "401 401 T Mon Oct 5 20:00:00 2026 /usr/bin/claude\n"
            "402 402 T Mon Oct 5 20:01:00 2026 /usr/bin/claude\n"
        ),
    )
    monkeypatch.setattr(handoff_shell.os, "getpgrp", lambda: 999)

    with pytest.raises(
        ValueError, match=r"Found 2 stopped harness process groups.*refusing to guess"
    ):
        handoff_shell.stopped_job_on_tty("/dev/ttys2", "claude")


def test_channel_on_tty_refuses_multiple_attached_live_lemons(monkeypatch):
    entries = [
        SimpleNamespace(channel="claude:one", path=Path("/one")),
        SimpleNamespace(channel="claude:two", path=Path("/two")),
    ]
    rows = [
        SimpleNamespace(channel=entry.channel, metadata={"tty": "/dev/ttys2"}) for entry in entries
    ]
    monkeypatch.setattr(handoff_shell.attached, "everything", lambda *_: entries)
    monkeypatch.setattr(handoff_shell.self_session, "_live_newest_rows", lambda *_: rows)

    with pytest.raises(LookupError, match=r"found 2.*Refusing to guess"):
        handoff_shell.channel_on_tty(None, "/dev/ttys2")


def test_process_group_on_tty(monkeypatch):
    monkeypatch.setattr(
        handoff_shell.subprocess,
        "run",
        lambda *_args, **_kwargs: _ps("11 S+\n12 R+\n"),
    )
    assert handoff_shell.process_group_on_tty(12, "/dev/ttys2") is True
    assert handoff_shell.process_group_on_tty(13, "/dev/ttys2") is False


def test_process_group_on_tty_treats_empty_macos_ps_result_as_exited(monkeypatch):
    monkeypatch.setattr(
        handoff_shell.subprocess,
        "run",
        lambda *_args, **_kwargs: _ps("", returncode=1, stderr="ps: no processes found"),
    )
    assert handoff_shell.process_group_on_tty(12, "/dev/ttys2") is False


def test_process_group_on_tty_ignores_zombies(monkeypatch):
    monkeypatch.setattr(
        handoff_shell.subprocess,
        "run",
        lambda *_args, **_kwargs: _ps("12 Z+\n"),
    )
    assert handoff_shell.process_group_on_tty(12, "/dev/ttys2") is False


def test_process_group_on_tty_stays_alive_with_non_zombie_member(monkeypatch):
    monkeypatch.setattr(
        handoff_shell.subprocess,
        "run",
        lambda *_args, **_kwargs: _ps("12 Z+\n12 S+\n"),
    )
    assert handoff_shell.process_group_on_tty(12, "/dev/ttys2") is True


@pytest.fixture(params=("sh", "bash", "fish"))
def interactive_shell(request):
    shell = shutil.which(request.param)
    if not shell:
        pytest.skip(f"{request.param} is not installed")
    if request.param == "fish":
        argv = [shell, "-N", "-i", "-C", 'function fish_prompt; printf "TTY_HANDOFF> "; end']
    elif request.param == "bash":
        argv = [shell, "--noprofile", "--norc", "-i"]
    else:
        argv = [shell, "-i"]
    return shell, argv, request.param != "sh"


@pytest.mark.parametrize("target_accepts", [True, False], ids=["accept", "rollback"])
def test_bare_cli_handoff_runs_in_same_terminal_and_recovers(
    tmp_path: Path, target_accepts: bool, interactive_shell
):
    """Run the real CLI handler from different interactive shells in isolated PTYs."""
    root = Path(__file__).resolve().parents[3]
    db_path = tmp_path / "inbox.db"
    briefs_dir = tmp_path / "briefs"
    briefs_dir.mkdir()
    brief = briefs_dir / "brief.md"
    source_pidfile = tmp_path / "source-pid"
    source_ready = tmp_path / "source-ready"
    target_started = tmp_path / "target-started"
    source_resumed = tmp_path / "source-resumed"

    source = tmp_path / "source.py"
    source.write_text(
        "import os, sqlite3, sys, time\n"
        "db, pidfile, ready = sys.argv[1:4]\n"
        "open(pidfile, 'w').write(f'{os.getpid()} {os.getpgrp()}')\n"
        "open(ready, 'w').close()\n"
        "while True:\n"
        "    try:\n"
        "        conn = sqlite3.connect(db)\n"
        "        row = conn.execute(\"select token, path from brief_handoffs where source = 'python:old' and phase = 'requested'\").fetchone()\n"
        "        conn.close()\n"
        "    except sqlite3.OperationalError:\n"
        "        row = None\n"
        "    if row:\n"
        "        token, path = row\n"
        "        inboxes = __import__('pathlib').Path(os.environ['LEMONAID_MESSAGES_DIR'])\n"
        "        messages = [p.read_text() for p in inboxes.glob('*/*.md')]\n"
        "        if not any(token in message for message in messages): time.sleep(.02); continue\n"
        "        text = open(path).read().replace('Old notes.', f'New notes.\\nHandoff-Ready: {token}')\n"
        "        open(path, 'w').write(text)\n"
        "        os.write(1, b'SOURCE_READY\\n')\n"
        "        break\n"
        "    time.sleep(.02)\n"
    )
    target = tmp_path / "target.py"
    target.write_text(
        "import os, sys\n"
        "from lemonaid.brief import handoff_coordinator, handoff_state\n"
        "from lemonaid.inbox import db\n"
        f"open({str(target_started)!r}, 'w').write('started')\n"
        "os.write(1, b'TARGET_STARTED\\n')\n"
        "if os.environ.get('TEST_ACCEPT_TARGET') == '1':\n"
        "    token = os.environ['LEMONAID_HANDOFF_TOKEN']\n"
        "    with db.connect() as conn:\n"
        "        db.add(conn, 'codex:new', 'target', metadata={'session_id': 'new', 'cwd': os.getcwd()}, status='read')\n"
        "        handoff_state.bind_target(conn, token, 'codex:new')\n"
        "        handoff_state.acknowledge(conn, token, 'codex:new', 'accept')\n"
        "        handoff_coordinator.advance(conn, token)\n"
    )
    resume = tmp_path / "resume.py"
    resume.write_text(
        f"import os; open({str(source_resumed)!r}, 'w').write('resumed'); "
        "os.write(1, b'SOURCE_RESUMED\\n')\n"
    )
    driver = tmp_path / "driver.py"
    driver.write_text(
        "import argparse, os, shlex, subprocess, sys\n"
        "from unittest.mock import Mock\n"
        "from lemonaid.brief import attached, handoff_cli, handoff_launch, handoff_shell, store\n"
        "from lemonaid.inbox import db\n"
        "from lemonaid.resume import build_resume_command\n"
        "tty = os.ttyname(0)\n"
        f"path = {str(brief)!r}\n"
        "lemon_id = store.new_lemon_id(__import__('pathlib').Path(path))\n"
        "open(path, 'w').write(f'# Test\\n\\nStatus: working\\n\\nLemon-ID: {lemon_id}\\n\\n## Now\\n\\n### Next\\n\\n- Continue.\\n\\n## Handoff\\n\\nOld notes.\\n')\n"
        "with db.connect() as conn:\n"
        "    conn.execute('INSERT INTO lemon_identities VALUES (?, ?)', (path, lemon_id))\n"
        "    db.add(conn, 'python:old', 'source', metadata={'session_id': 'old', 'cwd': os.getcwd(), 'tty': tty}, status='read')\n"
        "    attached.attach(conn, 'python:old', __import__('pathlib').Path(path))\n"
        f"source_pid, source_pgid = map(int, open({str(source_pidfile)!r}).read().split())\n"
        "process = handoff_shell._job_process(source_pid)\n"
        "assert process and 'T' in process[2], process\n"
        f"handoff_launch.configured_line = lambda *_: shlex.join([sys.executable, {str(target)!r}])\n"
        f"handoff_cli.build_resume_command = lambda *_: (os.getcwd(), [sys.executable, {str(resume)!r}])\n"
        "from lemonaid.cli import main\n"
        "real_popen = subprocess.Popen\n"
        "def fake_popen(*args, **kwargs):\n"
        "    if kwargs.get('start_new_session') and 'handoff' in args[0]: return Mock()\n"
        "    return real_popen(*args, **kwargs)\n"
        "subprocess.Popen = fake_popen\n"
        "os.environ['TEST_ACCEPT_TARGET'] = os.environ['TEST_ACCEPT_TARGET']\n"
        "sys.argv = ['lemonaid', 'brief', 'handoff', '--to', 'codex']\n"
        "main()\n"
    )

    child_env = {**os.environ}
    child_env.pop("TMUX_PANE", None)
    child_env.pop("LEMONAID_CHANNEL", None)
    child_env.pop("CODEX_THREAD_ID", None)
    child_env.pop("CLAUDE_CODE_SESSION_ID", None)
    isolated_home = tmp_path / "home"
    isolated_home.mkdir()
    isolated_messages = tmp_path / "messages"
    child_env.update(
        {
            "HOME": str(isolated_home),
            "LEMONAID_MESSAGES_DIR": str(isolated_messages),
            "LEMONAID_BRIEFS_DIR": str(briefs_dir),
            "LEMONAID_DB": str(db_path),
            "PYTHONPATH": str(root / "src"),
            "SHELL": interactive_shell[0],
            "TEST_ACCEPT_TARGET": "1" if target_accepts else "0",
            "PS1": "TTY_HANDOFF> ",
            "TERM": "dumb",
        }
    )
    if interactive_shell[2]:
        child_env["TMUX_PANE"] = "%42"
    pid, fd = pty.fork()
    if pid == 0:
        os.execve(interactive_shell[0], interactive_shell[1], child_env)

    output = bytearray()
    prompt = b"TTY_HANDOFF> "

    def until(needle: bytes, timeout: float = 10) -> bytes:
        deadline = time.monotonic() + timeout
        while needle not in output and time.monotonic() < deadline:
            if select.select([fd], [], [], 0.1)[0]:
                try:
                    output.extend(os.read(fd, 4096))
                except OSError:
                    break
        assert needle in output, bytes(output).decode(errors="replace")
        end = output.index(needle) + len(needle)
        result = bytes(output[:end])
        del output[:end]
        return result

    try:
        until(prompt)
        os.write(
            fd, f"{sys.executable} {source} {db_path} {source_pidfile} {source_ready}\r".encode()
        )
        deadline = time.monotonic() + 8
        while not source_ready.exists() and time.monotonic() < deadline:
            if select.select([fd], [], [], 0.1)[0]:
                output.extend(os.read(fd, 4096))
        assert source_ready.exists(), bytes(output).decode(errors="replace")
        os.write(fd, b"\x1a")
        stopped = until(prompt)
        source_pid, source_pgid = map(int, source_pidfile.read_text().split())
        process = handoff_shell._job_process(source_pid)
        assert process and process[0] == source_pgid and "T" in process[2], (stopped, process)
        os.write(fd, f"{sys.executable} {driver}\r".encode())
        until(b"TARGET_STARTED", 15)
        if not target_accepts:
            until(b"SOURCE_RESUMED", 10)
        until(prompt, 10)
        os.write(fd, b"jobs\r")
        jobs = until(prompt)
        assert b"suspended" not in jobs.lower() and b"stopped" not in jobs.lower(), jobs
        assert target_started.exists()
        assert source_resumed.exists() is (not target_accepts)
        with db.connect(db_path) as conn:
            from lemonaid.brief import attached, handoff_state

            handoff = conn.execute("SELECT token FROM brief_handoffs").fetchone()
            assert handoff is not None
            phase = handoff_state.get(conn, handoff["token"])["phase"]
            if target_accepts:
                assert phase == "complete"
                assert attached.by_channel(conn, ["codex:new"])["codex:new"] == brief
            else:
                assert phase == "failed"
                assert attached.by_channel(conn, ["python:old"])["python:old"] == brief
    finally:
        with suppress(OSError):
            if source_pidfile.exists():
                _, source_pgid = map(int, source_pidfile.read_text().split())
                os.killpg(source_pgid, signal.SIGKILL)
        with suppress(OSError):
            os.killpg(pid, signal.SIGKILL)
        with suppress(OSError):
            os.close(fd)
