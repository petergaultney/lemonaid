"""The nvim client (`src/lemonaid/lsp/nvim`), driven in headless nvim by `nvim/client.lua`
against a real `lemonaid lsp`. Skipped without nvim 0.12."""

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from lemonaid.lsp import cli

_SCRIPT = Path(__file__).parent / "nvim" / "client.lua"


def _nvim_0_12() -> bool:
    nvim = shutil.which("nvim")
    if nvim is None:
        return False
    version = subprocess.run([nvim, "--version"], capture_output=True, text=True).stdout
    found = re.match(r"NVIM v(\d+)\.(\d+)", version)
    return found is not None and (int(found[1]), int(found[2])) >= (0, 12)


@pytest.mark.skipif(not _nvim_0_12(), reason="needs nvim 0.12")
def test_the_nvim_client(tmp_path) -> None:
    (tmp_path / ".git").mkdir()
    config = tmp_path / "config.toml"
    config.write_text('[comments]\nauthor = "Caleb Gregory"\n')
    with tempfile.TemporaryDirectory(prefix="lma-nv-", dir="/tmp") as state:
        environ = {
            **os.environ,
            "PATH": f"{Path(sys.executable).parent}{os.pathsep}{os.environ['PATH']}",
            "PLUGIN": str(cli._NVIM_CLIENT),
            "WORK": str(tmp_path),
            "LEMONAID_STATE_DIR": state,
            "LEMONAID_CONFIG": str(config),
            "XDG_STATE_HOME": str(tmp_path / "nvim-state"),
        }
        for name in ("TMUX", "TMUX_PANE", "WEZTERM_PANE", "CMUX_SURFACE_ID"):
            environ.pop(name, None)
        nvim = subprocess.run(
            ["nvim", "--headless", "--clean", "-u", str(_SCRIPT)],
            cwd=tmp_path,
            env=environ,
            capture_output=True,
            text=True,
            timeout=180,
        )

    results = tmp_path / "results.txt"
    assert results.exists(), nvim.stdout[-2000:] + nvim.stderr[-2000:]
    failures = [line for line in results.read_text().splitlines() if line.startswith("FAIL")]
    assert failures == []
