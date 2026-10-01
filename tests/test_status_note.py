"""The once-a-turn PostToolUse reminder for a Claude lemon whose brief waits on Peter."""

import json
import os
import subprocess
from pathlib import Path

import pytest

from lemonaid.brief import attached
from lemonaid.brief import store as brief_store
from lemonaid.claude import install_hooks, status_note
from lemonaid.inbox import db

_SESSION = "abcd1234-0000-0000-0000-000000000000"
_BRIEF = "# lemon\n\nStatus: {status}\n\n## Now\n\n### Needs Peter\n\n- **pick one:** a or b\n"


@pytest.fixture(autouse=True)
def _no_inherited_session_identity(monkeypatch):
    for name in ("LEMONAID_CHANNEL", "CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID", "TMUX_PANE"):
        monkeypatch.delenv(name, raising=False)


def _briefed(status: str = "blocked") -> Path:
    path = brief_store.briefs_dir() / "lemon.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_BRIEF.format(status=status))
    with db.connect() as conn:
        db.add(conn, "claude:abcd1234", "", metadata={"session_id": _SESSION})
        attached.attach(conn, "claude:abcd1234", path)
    return path


def _tool_call(capsys, prompt_id: str = "turn-1", **extra) -> str:
    status_note.handle(json.dumps({"session_id": _SESSION, "prompt_id": prompt_id, **extra}))
    out = capsys.readouterr().out
    if not out:
        return ""

    output = json.loads(out)["hookSpecificOutput"]
    assert output["hookEventName"] == "PostToolUse"
    return output["additionalContext"]


def test_the_first_tool_call_of_a_turn_gets_the_reminder_and_the_rest_do_not(capsys):
    _briefed()

    assert '`blocked`, on: "pick one"' in _tool_call(capsys)
    assert _tool_call(capsys) == ""
    assert '"pick one"' in _tool_call(capsys, prompt_id="turn-2")
    logged = [json.loads(line) for line in status_note.notes_log().read_text().splitlines()]
    assert [(n["session_id"], n["prompt_id"]) for n in logged] == [
        (_SESSION, "turn-1"),
        (_SESSION, "turn-2"),
    ]


def test_a_brief_that_does_not_wait_on_peter_gets_nothing(capsys):
    _briefed(status="working")

    assert _tool_call(capsys) == ""


def test_a_status_changed_mid_turn_is_not_looked_at_again(capsys):
    path = _briefed(status="working")
    assert _tool_call(capsys) == ""

    path.write_text(_BRIEF.format(status="blocked"))

    assert _tool_call(capsys) == ""
    assert _tool_call(capsys, prompt_id="turn-2") != ""


def test_no_brief_no_prompt_id_or_a_subagent_gets_nothing(capsys):
    assert _tool_call(capsys) == ""

    _briefed()
    assert _tool_call(capsys, prompt_id="") == ""
    assert _tool_call(capsys, prompt_id="turn-9", agent_id="sub-1") == ""
    status_note.handle("not json")
    assert capsys.readouterr().out == ""


def test_the_hook_installs_on_post_tool_use(tmp_path):
    settings = tmp_path / "settings.json"

    install_hooks.install("PostToolUse", install_hooks.STATUS_NOTE_COMMAND, settings)

    hooks = json.loads(settings.read_text())["hooks"]["PostToolUse"]
    assert hooks == [{"hooks": [{"type": "command", "command": install_hooks.STATUS_NOTE_COMMAND}]}]
    install_hooks.uninstall("PostToolUse", install_hooks.STATUS_NOTE_COMMAND, settings)
    assert "PostToolUse" not in json.loads(settings.read_text())["hooks"]


def _run_installed(tmp_path: Path, stdin: str) -> str:
    """Run the installed hook command; what the fake `lemonaid` it hands off to received."""
    bin_dir, received = tmp_path / "bin", tmp_path / "received"
    bin_dir.mkdir(exist_ok=True)
    fake = bin_dir / "lemonaid"
    fake.write_text(f'#!/bin/sh\ncat > "{received}"\n')
    fake.chmod(0o755)
    received.unlink(missing_ok=True)
    subprocess.run(
        install_hooks.STATUS_NOTE_COMMAND,
        shell=True,
        input=stdin,
        text=True,
        check=True,
        env={**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"},
    )
    return received.read_text() if received.exists() else ""


def test_the_installed_command_skips_a_seen_prompt_id_in_the_shell(tmp_path):
    seen = status_note._seen(_SESSION)
    seen.parent.mkdir(parents=True, exist_ok=True)
    seen.write_text("turn-1")
    output = '{\\"prompt_id\\": \\"turn-1\\"}'  # a key inside a string value
    repeat = f'{{"session_id": "{_SESSION}", "tool_response": "{output}", "prompt_id":"turn-1"}}'
    new = repeat.replace('"prompt_id":"turn-1"', '"prompt_id":"turn-2"')

    assert _run_installed(tmp_path, repeat) == ""
    assert _run_installed(tmp_path, new) == new
    assert _run_installed(tmp_path, '{"session_id": "x"}') == '{"session_id": "x"}'


def test_a_tool_response_carrying_the_seen_prompt_id_does_not_hide_a_new_turn(tmp_path):
    seen = status_note._seen(_SESSION)
    seen.parent.mkdir(parents=True, exist_ok=True)
    seen.write_text("turn-1")
    new = json.dumps(
        {"session_id": _SESSION, "prompt_id": "turn-2", "tool_response": {"prompt_id": "turn-1"}}
    )
    repeat = json.dumps(
        {"session_id": _SESSION, "prompt_id": "turn-1", "tool_response": {"prompt_id": "turn-1"}}
    )

    assert _run_installed(tmp_path, new) == new
    assert _run_installed(tmp_path, repeat) == ""
