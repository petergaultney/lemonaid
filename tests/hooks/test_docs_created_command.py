"""The installed Claude PostToolUse docs hook, which starts lemonaid only after a Write created a file."""

import json
import os
import subprocess
from pathlib import Path

from lemonaid.hooks import install


def _received(tmp_path: Path, event: dict) -> str:
    bin_dir, received = tmp_path / "bin", tmp_path / "received"
    bin_dir.mkdir(exist_ok=True)
    fake = bin_dir / "lemonaid"
    fake.write_text(f'#!/bin/sh\ncat > "{received}"\n')
    fake.chmod(0o755)
    received.unlink(missing_ok=True)
    subprocess.run(
        install.docs_created_command(),
        shell=True,
        input=json.dumps(event, separators=(",", ":")),
        text=True,
        check=True,
        env={**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"},
    )
    return received.read_text() if received.exists() else ""


def test_only_a_write_that_created_a_file_reaches_lemonaid(tmp_path):
    write = {"tool_name": "Write", "tool_input": {"file_path": "/n/a.md"}}

    created = _received(tmp_path, {**write, "tool_response": {"type": "create"}})
    assert json.loads(created)["tool_response"] == {"type": "create"}
    assert _received(tmp_path, {**write, "tool_response": {"type": "update"}}) == ""
    assert _received(tmp_path, {"tool_name": "Bash", "tool_input": {"command": "ls"}}) == ""
