"""The shell line that starts a lemon: a template's harness command, set up to start unattended.

Codex asks whether to trust a directory it hasn't seen, and whether to update,
before it reads a prompt, and a prompt passed as an argument is lost behind
those dialogs. Both are answered with `-c` overrides rather than keystrokes;
nothing is written to Codex's own config.
"""

import json
import shlex
from pathlib import Path

from ..config import TmuxSessionConfig


def template_window(config: TmuxSessionConfig, windows: list[str]) -> int:
    """The 0-based position in *windows* of the template's harness window."""
    configured = config.resume_window if config.harness_window is None else config.harness_window
    return max(0, min(configured, len(windows) - 1))


def _codex_flags(directory: Path) -> list[str]:
    return [
        "-c",
        f'projects={{{json.dumps(str(directory))}={{trust_level="trusted"}}}}',
        "-c",
        "check_for_update_on_startup=false",
    ]


def _is_codex(words: list[str]) -> bool:
    return bool(words) and Path(words[0]).name == "codex"


def unclaimable(line: str) -> str:
    """Why a brief waiting on a window can't reach the lemon *line* starts, or "".

    A Codex on the shared app-server reports no pane, so no inbox row says it
    is the one in the window.
    """
    words = shlex.split(line)
    if _is_codex(words) and "--no-daemon" not in words:
        return f"{line!r} runs Codex on the shared app-server, which can't be matched to its window to claim a brief; add --no-daemon to the template"

    return ""


def harness_line(line: str, directory: Path, prompt: str = "") -> str:
    """*line* with the flags its harness needs to start in *directory*, then *prompt*."""
    program, _, rest = line.strip().partition(" ")
    if _is_codex(shlex.split(program)):
        line = " ".join([program, *(shlex.quote(f) for f in _codex_flags(directory)), rest]).strip()

    return f"{line} {shlex.quote(prompt)}" if prompt else line
