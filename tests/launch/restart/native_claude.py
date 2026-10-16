"""Private native claude configuration for authenticated restart acceptance."""

import json
import os
import shlex
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from lemonaid.inbox import db


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
    (home / "settings.json").write_text(flags[-1])
    flags = flags[:-2]
    return binary, home, cwd, sid, flags, private_auth
