"""`place open` on a real tmux server: the prompt reaches the lemon, and its brief waits for it."""

import argparse
import contextlib
import json
import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path

import pytest

from lemonaid.brief import store
from lemonaid.config import Config, PlaceRoot, PlacesConfig, TmuxSessionConfig
from lemonaid.inbox import db
from lemonaid.places import cli, lifecycle
from lemonaid.tmux import session

_PROMPT = """Peter's "brief"; $HOME `whoami` \\n it's here"""


def _shell(name: str) -> str | None:
    """*name* on PATH, or the login shell if it is that shell (xonsh often isn't on PATH)."""
    login = os.environ.get("SHELL", "")
    return shutil.which(name) or (login if Path(login).name == name else None)


@pytest.fixture
def tmux(monkeypatch):
    """A private tmux server, which plain `tmux` commands in lemonaid reach through $TMUX."""
    if not shutil.which("tmux"):
        pytest.skip("tmux not installed")

    name = f"lemonaid-test-{uuid.uuid4().hex[:8]}"

    def run(*args: str) -> str:
        return subprocess.run(
            ["tmux", "-L", name, *args], capture_output=True, text=True
        ).stdout.strip()

    subprocess.run(
        ["tmux", "-L", name, "-f", "/dev/null", "new-session", "-d", "-s", "base", "sleep 600"],
        check=True,
    )
    monkeypatch.setenv("TMUX", f"{run('display', '-p', '#{socket_path}')},0,0")
    try:
        yield run
    finally:
        run("kill-server")


def _recorder(tmp_path: Path) -> tuple[str, Path]:
    """A harness command that writes its arguments to a file, and that file."""
    out = tmp_path / "argv.json"
    script = tmp_path / "harness"
    script.write_text(
        f"#!/usr/bin/env python3\nimport json, sys\nopen({str(out)!r}, 'w').write(json.dumps(sys.argv[1:]))\n"
    )
    script.chmod(0o755)
    return str(script), out


def _wait_for(path: Path, seconds: float = 30) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if path.exists() and path.read_text():
            return True
        time.sleep(0.1)
    return False


@pytest.mark.parametrize("shell", ["sh", "bash", "zsh", "fish", "xonsh"])
def test_the_prompt_reaches_the_harness_as_one_argument(tmux, tmp_path, shell):
    """xonsh reads POSIX quoting (`'Peter'"'"'s'`) as a syntax error, so the lemon never started."""
    path = _shell(shell)
    if not path:
        pytest.skip(f"{shell} not installed")

    tmux("set-option", "-g", "default-shell", path)
    harness, out = _recorder(tmp_path)
    config = TmuxSessionConfig(templates={"default": ["", harness]}, resume_window=1)

    error = session.spawn_session(
        str(tmp_path), config, session_name="work", attach=False, initial_prompt=_PROMPT
    )

    assert error is None
    assert _wait_for(out), tmux("capture-pane", "-p", "-t", "work:1")
    assert json.loads(out.read_text()) == [_PROMPT]


def test_a_one_command_harness_does_not_inherit_the_prompt(tmux, tmp_path):
    out = tmp_path / "env.json"
    script = tmp_path / "harness"
    script.write_text(
        "#!/usr/bin/env python3\nimport json, os\n"
        f"open({str(out)!r}, 'w').write(json.dumps('LEMONAID_PROMPT' in os.environ))\n"
    )
    script.chmod(0o755)
    config = TmuxSessionConfig(templates={"default": ["", str(script)]}, resume_window=1)

    session.spawn_session(
        str(tmp_path), config, session_name="work", attach=False, initial_prompt="go"
    )

    assert _wait_for(out)
    assert json.loads(out.read_text()) is False


def test_a_prompt_in_the_first_window_does_not_reach_the_others(tmux, tmp_path):
    harness, out = _recorder(tmp_path)
    config = TmuxSessionConfig(templates={"default": [harness, ""]}, harness_window=0)

    session.spawn_session(
        str(tmp_path), config, session_name="work", attach=False, initial_prompt="go"
    )

    assert _wait_for(out)
    assert json.loads(out.read_text()) == ["go"]
    assert "LEMONAID_PROMPT=" not in tmux("show-environment", "-t", "work")


def _args(**kwargs) -> argparse.Namespace:
    return argparse.Namespace(
        **{
            "key": "feat/new",
            "root": None,
            "detach": True,
            "json": True,
            "harness": "default",
            "prompt": "",
            "no_check": False,
            "brief": "",
            "parent": "",
            "name": "",
            "group": [],
            **kwargs,
        }
    )


def test_a_brief_finds_the_new_session_when_another_pane_reports_its_directory(
    monkeypatch, capsys, tmux, tmp_path
):
    """The directory doesn't identify the session that was just opened.

    lemonaid's scratch pane, in whichever session the user is looking at, reports
    the directory of a command it runs, which can be the one just opened.
    """
    place = tmp_path / "feat" / "new"
    place.mkdir(parents=True)
    root = PlaceRoot(path=tmp_path, path_of=f"echo {tmp_path}/{{key}}")
    monkeypatch.setattr(
        cli,
        "load_config",
        lambda: Config(
            tmux_session=TmuxSessionConfig(
                templates={"default": ["", "sleep 600"]}, resume_window=1
            ),
            places=PlacesConfig(roots=[root]),
        ),
    )
    spawn = session.spawn_session

    def _spawn_then_a_pane_elsewhere_moves_in(**kwargs):
        error = spawn(**kwargs)
        tmux("new-window", "-d", "-t", "=base", "-c", str(place))
        return error

    monkeypatch.setattr(
        lifecycle.tmux.session, "spawn_session", _spawn_then_a_pane_elsewhere_moves_in
    )
    brief_file = store.briefs_dir() / "task.md"
    brief_file.parent.mkdir(parents=True)
    brief_file.write_text("# task\n\nStatus: working\n")

    with contextlib.suppress(SystemExit):
        cli.cmd_open(_args(root=str(tmp_path), brief="task"))

    opened = json.loads(capsys.readouterr().out)
    assert opened["error"] is None
    assert opened["session"] == "feat/new"
    with db.connect() as conn:
        [waiting] = conn.execute("SELECT * FROM pending_briefs").fetchall()
    assert (waiting["tmux_session"], waiting["tmux_window"]) == ("feat/new", "1")
