"""Private native codex configuration for authenticated restart acceptance."""

import json
import os
import shlex
import shutil
import sys
from pathlib import Path

import pytest

from lemonaid.inbox import db


def prepare(tmp_path, monkeypatch):
    binary = shutil.which("codex")
    auth = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "auth.json"
    if not binary or not auth.is_file() or not shutil.which("tmux"):
        pytest.skip("installed Codex, authentication and tmux required")
    home = tmp_path / "codex"
    home.mkdir(mode=0o700)
    private_auth = home / "auth.json"
    shutil.copyfile(auth, private_auth)
    private_auth.chmod(0o600)
    cwd = tmp_path / "project"
    cwd.mkdir()
    (home / "restart_canary.config.toml").write_text(f"""check_for_update_on_startup = false
model = "gpt-6.1-sol"
model_provider = "openai"
model_reasoning_effort = "high"
sandbox_mode = "read-only"
approval_policy = "on-request"
[projects.{json.dumps(str(cwd))}]
trust_level = "trusted"
[tui]
screen_reader_detection_done = true
[tui.model_availability_nux]
"gpt-6.1-sol" = 100
""")
    (home / "config.toml").write_text((home / "restart_canary.config.toml").read_text())
    (home / "hooks.json").write_text(
        json.dumps(
            {
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
                                            "codex",
                                        ]
                                    ),
                                }
                            ]
                        }
                    ]
                }
            }
        )
    )
    monkeypatch.setenv("LEMONAID_DB", str(db.get_db_path()))
    monkeypatch.setenv("CODEX_HOME", str(home))
    monkeypatch.delenv("LEMONAID_RESTART_TOKEN", raising=False)
    flags = [
        "--no-daemon",
        "--dangerously-bypass-hook-trust",
        "--profile",
        "restart_canary",
        "--model",
        "gpt-6.1-sol",
        "--sandbox",
        "read-only",
        "--ask-for-approval",
        "on-request",
        "-c",
        'model_reasoning_effort="high"',
        "-c",
        'model_provider="openai"',
    ]
    prompt = "Use the shell tool to run pwd, then reply exactly RESTART_CANARY_BEFORE. Do not read or change any other files."
    return binary, home, cwd, flags, prompt, private_auth
