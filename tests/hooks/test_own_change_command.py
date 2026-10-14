"""The installed own-change hook command, which starts Python only when there may be something to record."""

import json
import os
import subprocess
from pathlib import Path

import pytest

from lemonaid.hooks import install

_SESSION = "11111111-2222-3333-4444-555555555555"


def _run_installed(tmp_path: Path, stdin: str, harness: str = "claude") -> str:
    """Run the installed hook command; what the fake `lemonaid` it hands off to received."""
    bin_dir, received = tmp_path / "bin", tmp_path / "received"
    bin_dir.mkdir(exist_ok=True)
    fake = bin_dir / "lemonaid"
    fake.write_text(f'#!/bin/sh\necho "$@" > "{received}.args"\ncat > "{received}"\n')
    fake.chmod(0o755)
    received.unlink(missing_ok=True)
    subprocess.run(
        install.own_change_command(harness),
        shell=True,
        input=stdin,
        text=True,
        check=True,
        env={
            **os.environ,
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "LEMONAID_STATE_DIR": str(tmp_path / "state"),
        },
    )
    return received.read_text() if received.exists() else ""


def _event(command: str = "python3 rewrite.py") -> str:
    return json.dumps(
        {
            "session_id": _SESSION,
            "hook_event_name": "PostToolUse",
            "tool_use_id": "toolu_1",
            "tool_input": {"command": command},
        }
    )


def _writer_dir(tmp_path: Path, harness: str = "claude") -> Path:
    path = tmp_path / "state" / "own-edits" / f"{harness}-{_SESSION}"
    path.mkdir(parents=True)
    return path


def test_a_session_that_never_ran_a_waiter_stays_in_the_shell(tmp_path):
    assert _run_installed(tmp_path, _event()) == ""


@pytest.mark.parametrize("harness", ["claude", "codex"])
def test_a_session_watching_a_doc_hands_every_tool_call_to_python(tmp_path, harness):
    (_writer_dir(tmp_path, harness) / "abc.doc").write_text("/vault/review.md")

    assert _run_installed(tmp_path, _event(), harness) == _event()
    assert (tmp_path / "received.args").read_text().split() == [
        "hooks",
        "own-change",
        "--harness",
        harness,
    ]


def test_a_session_watching_only_prs_hands_over_only_pushes(tmp_path):
    _writer_dir(tmp_path)

    assert _run_installed(tmp_path, _event()) == ""
    assert _run_installed(tmp_path, _event("git push")) == _event("git push")


def test_the_hooks_install_for_every_tool(tmp_path):
    settings = tmp_path / "settings.json"
    install.install("claude", settings)

    hooks = json.loads(settings.read_text())["hooks"]
    assert hooks["PreToolUse"] == [
        {"hooks": [{"type": "command", "command": install.own_change_command("claude")}]}
    ]
    assert hooks["PostToolUse"] == hooks["PreToolUse"]
