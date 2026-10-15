"""Private native claude configuration for authenticated restart acceptance."""

import json
import os
import shlex
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

from lemonaid.config import Config
from lemonaid.inbox import db
from lemonaid.launch.restart import native, pane, planning, process


def prepare(tmp_path, monkeypatch, session_hook):
    binary = shutil.which("claude")
    if not binary or not shutil.which("tmux"):
        pytest.skip("installed Claude and tmux required")
    home = tmp_path / "claude"
    home.mkdir(mode=0o700)
    cwd = tmp_path / "project"
    cwd.mkdir()
    source_config = Path.home() / ".claude.json"
    original = json.loads(source_config.read_text()) if source_config.is_file() else {}
    config = {
        k: original[k]
        for k in ("oauthAccount", "hasCompletedOnboarding", "lastOnboardingVersion", "theme")
        if k in original
    }
    config["hasCompletedOnboarding"] = True
    config["projects"] = {str(cwd): {"hasTrustDialogAccepted": True}}
    (home / ".claude.json").write_text(json.dumps(config))
    credentials = (
        Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude") / ".credentials.json"
    )
    private_auth = home / ".credentials.json"
    if credentials.is_file():
        shutil.copyfile(credentials, private_auth)
    elif shutil.which("security"):
        result = subprocess.run(
            ["security", "find-generic-password", "-s", "Claude Code-credentials", "-w"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode:
            pytest.skip("Claude credentials unavailable to private canary")
        private_auth.write_text(result.stdout.strip())
    else:
        pytest.skip("Claude credentials unavailable to private canary")
    private_auth.chmod(0o600)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(home))
    monkeypatch.setenv("LEMONAID_DB", str(db.get_db_path()))
    monkeypatch.delenv("LEMONAID_RESTART_TOKEN", raising=False)
    sid = str(uuid.uuid4())
    flags = [
        "--model",
        "sonnet",
        "--permission-mode",
        "default",
        "--settings",
        json.dumps(
            {
                "crossSessionInbound": "accept",
                "permissions": {
                    "allow": ["Bash(lemonaid inbox *)", "Bash(lemonaid watch *)", "Bash(sleep *)"]
                },
                "statusLine": {
                    "type": "command",
                    "command": shlex.join(
                        [
                            sys.executable,
                            "-c",
                            'import json,sys;from lemonaid.claude.context_window import save;d=json.load(sys.stdin);save(d);print(d["model"]["id"])',
                        ]
                    ),
                },
                "hooks": {
                    "SessionStart": [
                        {
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": shlex.join(
                                        [
                                            sys.executable,
                                            "-m",
                                            "lemonaid",
                                            "hooks",
                                            "session-start",
                                            "--harness",
                                            "claude",
                                        ]
                                    ),
                                }
                            ]
                        }
                    ]
                    if session_hook
                    else []
                },
            }
        ),
    ]
    return binary, home, cwd, sid, flags, private_auth


def select_model(socket, target, channel, model, identity):
    # A UI selection after the last completed turn must be preserved or refused.
    pane.run(socket, "send-keys", "-t", target.pane, "-l", "/model opus")
    time.sleep(1)
    pane.run(socket, "send-keys", "-t", target.pane, "Enter")
    time.sleep(0.5)
    if "Yes, switch to Opus" in pane.run(socket, "capture-pane", "-p", "-t", target.pane):
        pane.run(socket, "send-keys", "-t", target.pane, "Enter")
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        with db.connect() as conn:
            selected = native.registered(conn, channel)["settings"]
        if selected.get("error") or selected.get("model") != model:
            break
        time.sleep(0.2)
    assert selected.get("error") or selected.get("model") != model, pane.run(
        socket, "capture-pane", "-p", "-t", target.pane
    )
    with db.connect() as conn:
        if selected.get("error"):
            with pytest.raises(ValueError):
                planning.build(conn, channel, Config(), force=True)
        else:
            selected_plan = planning.build(conn, channel, Config(), force=True)
            assert selected_plan["settings"]["model"] == selected["model"]
            assert (
                selected_plan["argv"][selected_plan["argv"].index("--model") + 1]
                == selected["model"]
            )
    assert process.same(identity)
