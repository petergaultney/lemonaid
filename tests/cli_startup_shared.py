"""Isolated fresh-process execution for CLI import checks."""

import os
import subprocess
import sys
import textwrap
from pathlib import Path


def run(tmp_path: Path, code: str, stdin: str = "") -> None:
    env = {
        **os.environ,
        **{
            name: str(tmp_path / path)
            for name, path in (
                ("LEMONAID_DB", "inbox.db"),
                ("LEMONAID_CONFIG", "config.toml"),
                ("LEMONAID_STATE_DIR", "state"),
                ("LEMONAID_MESSAGES_DIR", "messages"),
                ("LEMONAID_LEMONS_DIR", "lemons"),
                ("LEMONAID_LEGACY_BRIEFS_DIR", "legacy-briefs"),
                ("LEMONAID_WATCH_LISTS_DIR", "watch-lists"),
                ("TMPDIR", "tmp"),
                ("LEMONAID_LOG", "lemonaid.log"),
                ("LEMONAID_BRIEFS_DIR", "briefs"),
                ("LEMONAID_CLAUDE_SKILLS_DIR", "claude-skills"),
                ("LEMONAID_CODEX_SKILLS_DIR", "codex-skills"),
            )
        },
        "TMUX": "/nonexistent/lemonaid-lazy-import-tests,0,0",
    }
    (tmp_path / "tmp").mkdir(exist_ok=True)
    for name in (
        "LEMONAID_CHANNEL",
        "CLAUDE_CODE_SESSION_ID",
        "CODEX_THREAD_ID",
        "TMUX_PANE",
        "LEMONAID_HANDOFF_TOKEN",
    ):
        env.pop(name, None)
    done = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        env=env,
        cwd=tmp_path,
        input=stdin,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert done.returncode == 0, done.stdout + done.stderr
