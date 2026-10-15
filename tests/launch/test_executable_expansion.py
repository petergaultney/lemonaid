import os
import subprocess

import pytest

from lemonaid.launch import command


@pytest.mark.parametrize("harness", ["codex", "claude"])
@pytest.mark.parametrize("prefix", ["$REVIEW_BIN", '"$REVIEW_BIN"', "~/.local/bin"])
def test_legacy_executable_expansion_survives_startup_overrides(tmp_path, harness, prefix):
    directory = tmp_path / ".local" / "bin"
    directory.mkdir(parents=True)
    executable = directory / harness
    executable.write_text("#!/bin/sh\nprintf executed")
    executable.chmod(0o755)
    line, _ = command.harness_line(f"{prefix}/{harness} --no-daemon", tmp_path, title="Task")
    result = subprocess.run(
        ["/bin/sh", "-c", line],
        env={**os.environ, "REVIEW_BIN": str(directory), "HOME": str(tmp_path)},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (line, result.stderr)
    assert result.stdout == "executed"
