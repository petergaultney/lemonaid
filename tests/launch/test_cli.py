"""`lemon start`: a lemon in a window of an existing session, never over a live one."""

import argparse
import contextlib
import json
import shutil
import subprocess
import time
import uuid
from pathlib import Path

import pytest

from lemonaid.brief import store
from lemonaid.config import Config, TmuxSessionConfig
from lemonaid.inbox import db
from lemonaid.launch import cli


@pytest.fixture
def tmux(monkeypatch, tmp_path):
    """A private tmux server with session `work` in *tmp_path*."""
    if not shutil.which("tmux"):
        pytest.skip("tmux not installed")

    name = f"lemonaid-test-{uuid.uuid4().hex[:8]}"

    def run(*args: str) -> str:
        return subprocess.run(
            ["tmux", "-L", name, *args], capture_output=True, text=True
        ).stdout.strip()

    subprocess.run(
        [
            "tmux",
            "-L",
            name,
            "-f",
            "/dev/null",
            "new-session",
            "-d",
            "-s",
            "work",
            "-c",
            str(tmp_path),
        ],
        check=True,
    )
    monkeypatch.setenv("TMUX", f"{run('display', '-p', '#{socket_path}')},0,0")
    try:
        yield run
    finally:
        run("kill-server")


@pytest.fixture(autouse=True)
def _config(monkeypatch):
    config = Config(
        tmux_session=TmuxSessionConfig(templates={"default": ["", "echo lemon"]}, resume_window=1)
    )
    monkeypatch.setattr(cli, "load_config", lambda: config)


def _brief(name: str) -> Path:
    path = store.briefs_dir() / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {name}\n\nStatus: working\n")
    return path.resolve()


def _start(capsys, *argv: str) -> dict:
    parser = argparse.ArgumentParser()
    cli.add_parser(parser.add_subparsers())
    args = parser.parse_args(["start", "--json", "--no-check", *argv])
    with contextlib.suppress(SystemExit):
        args.func(args)
    return json.loads(capsys.readouterr().out)


def _screen(tmux, target: str, text: str) -> str:
    for _ in range(50):
        if text in (screen := tmux("capture-pane", "-p", "-t", target)):
            return screen
        time.sleep(0.1)
    return screen


def _pending() -> list[dict]:
    with db.connect() as conn:
        return [dict(row) for row in conn.execute("SELECT * FROM pending_briefs")]


def test_a_new_window_runs_the_template_line_and_waits_for_its_lemon(capsys, tmux, tmp_path):
    _brief("review")

    started = _start(capsys, "work:4", "--prompt", "go on", "--brief", "review", "--name", "REVIEW")

    assert started["error"] is None
    assert started["dir"] == str(tmp_path)
    assert "lemon go on" in _screen(tmux, "work:4", "lemon go on")
    [waiting] = _pending()
    assert (waiting["tmux_session"], waiting["tmux_window"]) == ("work", "4")
    assert (waiting["tmux_window_id"], waiting["name"]) == (started["window_id"], "REVIEW")


def test_a_live_window_is_refused(capsys, tmux):
    _brief("review")
    index = tmux("display", "-p", "-t", "=work:", "#{window_index}")

    refused = _start(capsys, f"work:{index}", "--brief", "review")

    assert "not replacing it" in refused["error"]
    assert not _pending()


def test_a_dead_window_is_respawned(capsys, tmux):
    tmux("set-option", "-g", "remain-on-exit", "on")
    tmux("new-window", "-d", "-t", "work:6", "true")
    for _ in range(50):
        if tmux("display", "-p", "-t", "work:6", "#{pane_dead}") == "1":
            break
        time.sleep(0.1)

    started = _start(capsys, "work:6")

    assert started["error"] is None
    assert "lemon" in _screen(tmux, "work:6", "lemon")


def test_a_missing_session_is_an_error(capsys, tmux):
    assert "No tmux session 'elsewhere'" in _start(capsys, "elsewhere:2")["error"]


def test_a_window_is_named_by_index(capsys, tmux):
    assert "by its index" in _start(capsys, "work:reviewer")["error"]


def test_name_needs_a_brief(capsys, tmux):
    assert "--name needs --brief" in _start(capsys, "work:4", "--name", "x")["error"]


def test_a_brief_for_a_codex_on_the_shared_daemon_is_refused_before_anything_starts(
    capsys, tmux, monkeypatch
):
    _brief("review")
    config = Config(
        tmux_session=TmuxSessionConfig(templates={"codex": ["", "codex"]}, resume_window=1)
    )
    monkeypatch.setattr(cli, "load_config", lambda: config)

    refused = _start(capsys, "work:4", "--harness", "codex", "--brief", "review")

    assert "--no-daemon" in refused["error"]
    assert not _pending()
    assert tmux("list-windows", "-t", "=work", "-F", "#{window_index}") == tmux(
        "display", "-p", "-t", "=work:", "#{window_index}"
    )
