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

from lemonaid.brief import attached, identity, store
from lemonaid.config import Config, TmuxSessionConfig
from lemonaid.inbox import db
from lemonaid.launch import cli
from lemonaid.lineage import links
from lemonaid.messages import store as messages_store


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


def test_a_brief_without_a_prompt_starts_the_lemon_on_the_default_prompt(capsys, tmux):
    _brief("review")

    started = _start(capsys, "work:4", "--brief", "review")

    assert started["error"] is None
    assert "read it all and do the work." in _screen(tmux, "work:4", "do the work.").replace(
        "\n", ""
    )


def test_parent_parent_starts_a_sibling_and_tells_the_parent(capsys, tmux, monkeypatch):
    monkeypatch.setenv("LEMONAID_CHANNEL", "claude:author")
    lead_path, author_path = _brief("lead"), _brief("author")
    with db.connect() as conn:
        db.add(conn, "claude:author", "", metadata={})
        attached.attach(conn, "claude:author", author_path)
        lead, author = identity.ensure(conn, lead_path), identity.ensure(conn, author_path)
        links.set_parent(conn, author, lead)
    _brief("review")

    started = _start(capsys, "work:4", "--brief", "review", "--parent", "parent")

    assert started["error"] is None
    assert started["parent"] == lead
    [line] = [path.read_text() for path in messages_store.mailbox_for_id(lead).iterdir()]
    assert author in line


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


def test_a_bare_window_starts_in_your_own_session_whatever_it_is_called_now(
    capsys, tmux, monkeypatch
):
    monkeypatch.setenv("TMUX_PANE", tmux("display", "-p", "-t", "work:", "#{pane_id}"))
    tmux("rename-session", "-t", "work", "renamed from the grove")

    started = _start(capsys, ":4")

    assert (started["error"], started["session"], started["window"]) == (
        None,
        "renamed from the grove",
        "4",
    )
    assert "lemon" in _screen(tmux, "renamed from the grove:4", "lemon")


def test_a_bare_window_outside_tmux_is_an_error(capsys, tmux, monkeypatch):
    monkeypatch.delenv("TMUX_PANE", raising=False)

    assert "isn't in tmux" in _start(capsys, ":4")["error"]


def test_a_brief_also_waits_on_the_launch_token_in_the_lemon_s_environment(
    capsys, tmux, monkeypatch
):
    config = Config(
        tmux_session=TmuxSessionConfig(
            templates={"default": ["", "printenv LEMONAID_LAUNCH_TOKEN"]}, resume_window=1
        )
    )
    monkeypatch.setattr(cli, "load_config", lambda: config)
    _brief("review")

    _start(capsys, "work:4", "--brief", "review")

    [waiting] = _pending()
    assert len(waiting["launch_token"]) == 16
    assert waiting["launch_token"] in _screen(tmux, "work:4", waiting["launch_token"])
    assert (waiting["tmux_session"], waiting["tmux_window"]) == ("work", "4")


def test_no_target_in_tmux_opens_the_next_window_of_your_session_and_says_where(
    capsys, tmux, monkeypatch, tmp_path
):
    monkeypatch.setenv("TMUX_PANE", tmux("display", "-p", "-t", "work:", "#{pane_id}"))
    monkeypatch.setenv("WEZTERM_PANE", "3")
    (tmp_path / "here").mkdir()
    monkeypatch.chdir(tmp_path / "here")
    _brief("review")
    first = tmux("display", "-p", "-t", "=work:", "#{window_index}")

    started = _start(capsys, "--brief", "review")

    index = str(int(first) + 1)
    assert (started["error"], started["front_end"], started["window"]) == (None, "tmux", index)
    assert started["where"] == f"tmux window work:{index}"
    assert started["dir"] == str(tmp_path / "here")
    assert "lemon" in _screen(tmux, f"work:{index}", "lemon")
    [waiting] = _pending()
    assert len(waiting["launch_token"]) == 16


def test_the_plain_output_says_where_the_lemon_went(capsys, tmux, monkeypatch):
    monkeypatch.setenv("TMUX_PANE", tmux("display", "-p", "-t", "work:", "#{pane_id}"))
    parser = argparse.ArgumentParser()
    cli.add_parser(parser.add_subparsers())
    args = parser.parse_args(["start", "--no-check"])

    args.func(args)

    assert capsys.readouterr().out.startswith("started default in tmux window work:")


def test_no_target_outside_tmux_wezterm_and_cmux_is_an_error(capsys, monkeypatch):
    for variable in ("TMUX_PANE", "WEZTERM_PANE", "CMUX_SURFACE_ID"):
        monkeypatch.delenv(variable, raising=False)

    assert "Not in tmux, WezTerm or cmux" in _start(capsys)["error"]


def test_no_target_in_cmux_opens_a_workspace_that_waits_on_its_token(capsys, monkeypatch, tmp_path):
    for variable in ("TMUX_PANE", "WEZTERM_PANE"):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("CMUX_SURFACE_ID", "S1")
    monkeypatch.setenv("SHELL", "/bin/zsh")
    monkeypatch.chdir(tmp_path)
    opened = []
    monkeypatch.setattr(
        cli.where.cmux.navigation,
        "open_workspace",
        lambda cwd, argv, name, focus=True: opened.append((cwd, argv, name, focus)) or True,
    )
    _brief("review")

    started = _start(capsys, "--brief", "review", "--name", "REVIEW")

    assert (started["error"], started["front_end"], started["where"]) == (
        None,
        "cmux",
        "cmux workspace REVIEW",
    )
    [(cwd, argv, name, focus)] = opened
    [waiting] = _pending()
    assert (cwd, name, focus) == (str(tmp_path), "REVIEW", False)
    assert argv[0] == "env" and argv[-3:-1] == ["/bin/zsh", "-c"]
    assert f"LEMONAID_LAUNCH_TOKEN={waiting['launch_token']}" in argv
    assert argv[-1].startswith("env -u LEMONAID_PROMPT echo lemon")


@pytest.fixture
def wezterm(monkeypatch, tmp_path) -> list[list[str]]:
    """`wezterm cli` answered as an instance where the caller is pane 3, in workspace `feat-x`."""
    calls: list[list[str]] = []
    out = {"spawn": "9\n", "list": json.dumps([{"pane_id": 9, "workspace": "feat-x"}])}

    def run(args, socket=None):
        calls.append(list(args))
        return subprocess.CompletedProcess(args, 0, out.get(args[0], ""), "")

    monkeypatch.setattr(cli.where.wezterm.client, "run", run)
    monkeypatch.setenv("WEZTERM_PANE", "3")
    monkeypatch.delenv("TMUX_PANE", raising=False)
    monkeypatch.chdir(tmp_path)
    return calls


def test_no_target_in_wezterm_opens_a_tab_beside_you_and_waits_on_its_token(
    capsys, wezterm, tmp_path
):
    _brief("review")

    started = _start(capsys, "--prompt", "go on", "--brief", "review")

    assert (started["error"], started["front_end"], started["dir"]) == (
        None,
        "wezterm",
        str(tmp_path),
    )
    assert started["where"] == "WezTerm pane 9 in workspace feat-x"
    spawn, _, typed = wezterm
    [waiting] = _pending()
    assert spawn[:5] == ["spawn", "--pane-id", "3", "--cwd", str(tmp_path)]
    assert f"LEMONAID_LAUNCH_TOKEN={waiting['launch_token']}" in spawn
    assert "LEMONAID_PROMPT=go on" in spawn
    assert typed[:4] == ["send-text", "--no-paste", "--pane-id", "9"]
    assert typed[4].startswith("env -u LEMONAID_PROMPT echo lemon")
    assert (waiting["tmux_session"], waiting["tmux_window"]) == ("", "")
